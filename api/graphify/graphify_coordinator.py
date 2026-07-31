"""Index coordination mixin for :class:`GraphifyManager`.

Extracted from ``manager.py`` — graph build/update subprocess execution,
single-index queue management, LLM environment construction, and extract
argument building.  Methods are defined on this mixin and inherited by
``GraphifyManager``; ``self`` is annotated as ``GraphifyManager`` so the type
checker sees the full combined-class interface.

Names that tests patch via ``api.graphify.manager.X`` (e.g.
``_is_module_importable``, ``_pip_path``) are routed through the manager
module at call time via ``_manager`` so that
``mock.patch("api.graphify.manager.X")`` takes effect even though the calling
code lives in this mixin module.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from .config import GraphifyProject
from .graphify_helpers import _directory_size, _format_bytes
from .graphify_probes import (
    _GRAPHIFY_BACKEND_ALIAS,
    _GRAPHIFY_LLM_ENV_KEYS,
    _GRAPHIFY_LLM_EXTRAS,
    _GRAPHIFY_OPENAI_EXTRA,
    _GRAPHIFY_OPENAI_SDK_BACKENDS,
    _GRAPHIFY_PROVIDER_KEY_FALLBACK,
    _looks_like_timeout_error,
    _strip_fcc_model_prefix,
)
from .projects import (
    load_project_registry,
    save_project_registry,
    update_project_status,
)

if TYPE_CHECKING:
    from .manager import GraphifyManager

# The manager module is always in ``sys.modules`` by the time any method is
# called (it imported this mixin).  See ``graphify_process.py`` for rationale.
import api.graphify.manager as _manager  # circular at import, safe at call


class CoordinatorMixin:
    """Index coordination methods.  Mixed into :class:`GraphifyManager`."""

    async def index_project(
        self: GraphifyManager, project: GraphifyProject
    ) -> dict[str, Any]:
        """Run ``graphify extract`` (or ``update`` if graph exists) for *project*."""
        setup_result = await self.setup(create_venv=True)
        if not setup_result["ready"]:
            return {
                "success": False,
                "error": setup_result.get("error", "Graphify not available"),
            }

        python = setup_result["python"]
        repo_path = Path(project.path)

        # Ensure the graphify venv has the LLM SDK the configured backend imports.
        # The venv is created with only graphifyy[mcp] (no openai/anthropic), so
        # without this every cloud backend raises ImportError mid-extract.
        try:
            await self._ensure_graphify_llm_extra(python)
        except Exception as exc:
            error = str(exc)
            registry = load_project_registry()
            update_project_status(
                registry, project.path, status="error", error_message=error
            )
            save_project_registry(registry)
            return {"success": False, "error": error}

        max_bytes = getattr(self._settings, "graphify_max_project_bytes", 0)
        if max_bytes > 0:
            size = _directory_size(repo_path)
            if size > max_bytes:
                error = (
                    f"Project size ({_format_bytes(size)}) exceeds "
                    f"GRAPHIFY_MAX_PROJECT_BYTES ({_format_bytes(max_bytes)})"
                )
                registry = load_project_registry()
                update_project_status(
                    registry, project.path, status="error", error_message=error
                )
                save_project_registry(registry)
                return {"success": False, "error": error}

        graph_out = repo_path / project.graphify_out / "graph.json"
        mode = "update" if graph_out.exists() else "extract"
        registry = load_project_registry()
        project_ref = update_project_status(registry, project.path, status="indexing")
        save_project_registry(registry)

        result = await self._run_extract_with_timeout_retry(python, project, mode)

        if not result["success"]:
            project_ref = update_project_status(
                registry, project.path, status="error", error_message=result["error"]
            )
            save_project_registry(registry)
            return result

        project_ref.status = "ready"
        project_ref.error_message = ""
        project_ref.last_indexed = datetime.now()
        save_project_registry(registry)
        return {
            "success": True,
            "mode": mode,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        }

    async def _run_extract_with_timeout_retry(
        self: GraphifyManager,
        python: str,
        project: GraphifyProject,
        mode: str,
    ) -> dict[str, Any]:
        """Run ``graphify extract``/``update``, bisecting chunks on timeout.

        Cloudflare Workers AI frequently times out on large chunks. Rather than
        failing the whole project, halve the token budget and retry until the
        chunk is small enough to complete. Only timeout errors are retried;
        other failures (missing key, import errors, etc.) surface immediately.
        """
        backend = self._settings.graphify_llm_backend.strip().lower()
        token_budget = self._default_token_budget(backend)
        min_budget = 4_096
        last_error = ""

        while token_budget >= min_budget:
            result = await self._run_extract_subprocess(
                python, project, mode, token_budget=token_budget
            )
            if result["success"]:
                return result

            last_error = result["error"]
            if not _looks_like_timeout_error(last_error):
                return result

            logger.warning(
                "GRAPHIFY_MANAGER: timeout for {} with token_budget={}; halving and retrying",
                project.path,
                token_budget,
            )
            token_budget //= 2

        return {"success": False, "error": last_error}

    async def _run_extract_subprocess(
        self: GraphifyManager,
        python: str,
        project: GraphifyProject,
        mode: str,
        *,
        token_budget: int,
    ) -> dict[str, Any]:
        """Run one ``graphify`` subprocess and return parsed result."""
        try:
            proc = await asyncio.create_subprocess_exec(
                python,
                *self._build_extract_args(project, mode, token_budget=token_budget),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._extract_env(),
            )
            stdout, stderr = await proc.communicate()
        except Exception as exc:
            return {"success": False, "error": str(exc), "stdout": "", "stderr": ""}

        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            error = stderr_text or stdout_text or f"graphify {mode} failed"
            return {
                "success": False,
                "error": error,
                "stdout": stdout_text,
                "stderr": stderr_text,
            }

        return {
            "success": True,
            "stdout": stdout_text,
            "stderr": stderr_text,
        }

    async def start_index_project(
        self: GraphifyManager, project: GraphifyProject
    ) -> dict[str, Any]:
        """Enqueue *project* for sequential background indexing.

        Only one project indexes at a time.  If another project is already
        indexing, *project* is queued and will start automatically when the
        current one finishes.
        """
        if self._index_current == project.path:
            return {
                "success": True,
                "status": "already_running",
                "path": project.path,
            }

        if project.path in self._index_queue_paths:
            return {
                "success": True,
                "status": "already_queued",
                "path": project.path,
            }

        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._index_queue.append((project, future))
        self._index_queue_paths.add(project.path)

        registry = load_project_registry()
        update_project_status(registry, project.path, status="queued")
        save_project_registry(registry)

        self._index_event.set()
        return {"success": True, "status": "queued", "path": project.path}

    def get_index_task_status(
        self: GraphifyManager, path: str
    ) -> dict[str, Any] | None:
        """Return in-progress or queued status for a background indexing task."""
        if self._index_current == path:
            return {"path": path, "status": "indexing"}

        for queued_project, future in self._index_queue:
            if queued_project.path == path:
                if future.done():
                    try:
                        result = future.result()
                    except Exception as exc:
                        return {
                            "path": path,
                            "status": "error",
                            "error_message": str(exc),
                        }
                    status = "ready" if result.get("success") else "error"
                    return {
                        "path": path,
                        "status": status,
                        "result": result,
                        "error_message": result.get("error", ""),
                    }
                return {"path": path, "status": "queued"}

        return None

    @property
    def index_queue_snapshot(self: GraphifyManager) -> list[dict[str, Any]]:
        """Return an ordered snapshot of the indexing queue for the API."""
        items: list[dict[str, Any]] = []
        if self._index_current:
            items.append({"path": self._index_current, "status": "indexing"})
        for project, future in self._index_queue:
            if future.done():
                try:
                    future.result()
                    status = "ready"
                except Exception:
                    status = "error"
            else:
                status = "queued"
            items.append({"path": project.path, "status": status})
        return items

    def _start_index_worker(self: GraphifyManager) -> None:
        """Launch the single-item index worker coroutine."""
        if self._index_worker_task is not None and not self._index_worker_task.done():
            return
        self._index_worker_task = asyncio.create_task(self._run_index_worker())

    async def _run_index_worker(self: GraphifyManager) -> None:
        """Process one project at a time from the queue."""
        while True:
            self._index_event.clear()
            if not self._index_queue:
                await self._index_event.wait()
                continue

            project, future = self._index_queue.popleft()
            self._index_queue_paths.discard(project.path)
            self._index_current = project.path
            self._index_current_future = future

            try:
                result = await self.index_project(project)
                if not future.done():
                    future.set_result(result)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            finally:
                self._index_current = None
                self._index_current_future = None

    async def _drain_index_queue(self: GraphifyManager) -> None:
        """Cancel all queued and in-flight index work, then stop the worker."""
        if self._index_worker_task is not None and not self._index_worker_task.done():
            self._index_worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._index_worker_task
            self._index_worker_task = None

        # Resolve the in-flight future if the worker was cancelled mid-index.
        if (
            self._index_current_future is not None
            and not self._index_current_future.done()
        ):
            self._index_current_future.set_exception(
                asyncio.CancelledError("Graphify stopped")
            )
        self._index_current_future = None

        while self._index_queue:
            _project, future = self._index_queue.popleft()
            if not future.done():
                future.set_exception(asyncio.CancelledError("Graphify stopped"))
        self._index_queue_paths.clear()
        self._index_current = None

    async def _auto_index_projects(self: GraphifyManager) -> None:
        registry = load_project_registry()
        for project in registry.projects:
            # Re-queue interrupted ``indexing`` projects: a server restart
            # mid-index leaves them orphaned with no running subprocess, so
            # they would never complete without a manual re-index.
            if project.status in {"missing", "stale", "error", "indexing"}:
                await self.start_index_project(project)

    def _resolve_llm_api_key(self: GraphifyManager, backend: str) -> str:
        """Return the API key for *backend*, reusing a Claude Unbound provider key.

        ``GRAPHIFY_LLM_API_KEY`` wins; when it is empty we fall back to the matching
        provider key already configured on the Providers tab (cloudflare/gemini/
        deepseek/kimi), so the user does not re-enter it.
        """
        key = self._settings.graphify_llm_api_key.strip()
        if key:
            return key
        attr = _GRAPHIFY_PROVIDER_KEY_FALLBACK.get(backend)
        if attr:
            return getattr(self._settings, attr, "").strip()
        return ""

    def _cloudflare_openai_base(self: GraphifyManager) -> str:
        """Return the Cloudflare Workers AI OpenAI-compatible base URL.

        Honours an explicit ``CLOUDFLARE_AI_BASE_URL`` override; otherwise composes
        ``https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/v1`` from
        the configured account id — the same endpoint Claude Unbound's own
        Cloudflare provider speaks.
        """
        override = self._settings.cloudflare_ai_base_url.strip()
        if override:
            return override
        account = self._settings.cloudflare_ai_account_id.strip()
        return f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1"

    def _extract_env(self: GraphifyManager) -> dict[str, str]:
        """Build the environment for ``graphify extract``/``update`` subprocesses.

        Inherits the parent environment and injects the configured LLM backend's
        credentials so the semantic pass over docs/PDFs/images and community naming
        can run. For ``cloudflare`` we redirect graphify's ``openai`` backend at the
        Cloudflare OpenAI-compatible endpoint via ``OPENAI_BASE_URL`` (graphify has
        no native cloudflare backend). The ``GRAPHIFY_API_KEY`` transport auth is
        irrelevant to the indexer.
        """
        env = os.environ.copy()
        backend = self._settings.graphify_llm_backend.strip().lower()
        if not backend:
            return env
        api_key = self._resolve_llm_api_key(backend)
        if backend == "cloudflare":
            env["OPENAI_API_KEY"] = api_key
            env["OPENAI_BASE_URL"] = self._cloudflare_openai_base()
            model = self._settings.graphify_llm_model.strip()
            if model:
                env["GRAPHIFY_OPENAI_MODEL"] = _strip_fcc_model_prefix(model)
            return env
        if backend == "lmstudio":
            # LM Studio serves an OpenAI-compatible API; graphify has no native
            # lmstudio backend so we ride its ``openai`` path via OPENAI_BASE_URL.
            # LM Studio does not require a real API key — the OpenAI SDK needs a
            # non-empty string to initialise.
            env["OPENAI_API_KEY"] = api_key or "lm-studio"
            env["OPENAI_BASE_URL"] = self._settings.lm_studio_base_url.strip()
            model = self._settings.graphify_llm_model.strip()
            if model:
                env["GRAPHIFY_OPENAI_MODEL"] = _strip_fcc_model_prefix(model)
            return env
        env_key = _GRAPHIFY_LLM_ENV_KEYS.get(backend)
        if env_key and api_key:
            env[env_key] = api_key
        return env

    def _build_extract_args(
        self: GraphifyManager,
        project: GraphifyProject,
        mode: str,
        *,
        token_budget: int | None = None,
    ) -> list[str]:
        """Return the ``graphify <mode> <path>`` argv after the python interpreter.

        ``--backend``/``--model`` apply only to ``extract`` (``update`` is code-only
        by nature). ``--backend`` is passed explicitly so graphify's
        ``detect_backend()`` precedence (gemini→kimi→claude→openai→…) cannot be
        shadowed by a stray key inherited from the parent environment; ``cloudflare``
        maps to graphify's ``openai`` backend.
        """
        args: list[str] = ["-m", "graphify", mode, project.path]
        if mode != "extract":
            return args
        if self._settings.graphify_code_only:
            args.append("--code-only")
            return args
        backend = self._settings.graphify_llm_backend.strip().lower()
        if backend:
            args.extend(["--backend", _GRAPHIFY_BACKEND_ALIAS.get(backend, backend)])
            model = self._settings.graphify_llm_model.strip()
            if model:
                args.extend(["--model", _strip_fcc_model_prefix(model)])
        if token_budget is None:
            token_budget = self._default_token_budget(backend)
        if token_budget > 0:
            args.extend(["--token-budget", str(token_budget)])
        return args

    def _default_token_budget(self: GraphifyManager, backend: str) -> int:
        """Return the default --token-budget for ``backend``.

        Cloudflare's Workers AI endpoint frequently times out on large chunks, so
        we default to a much smaller chunk size than graphify's 60k default.
        """
        if backend == "cloudflare":
            return 20_000
        return self._settings.graphify_token_budget

    async def _ensure_graphify_llm_extra(self: GraphifyManager, python: str) -> None:
        """Install the LLM SDK the configured backend imports into the graphify venv.

        The isolated venv is created with only ``graphifyy[mcp]`` (no ``openai`` or
        ``anthropic``), so every cloud backend would raise ``ImportError`` mid-extract.
        OpenAI-compatible backends (cloudflare/openai/gemini/kimi/deepseek/ollama) need
        the ``openai`` package; ``claude`` needs ``anthropic``. ``azure``/``bedrock``/
        ``claude-cli`` are out of scope for v1 (boto3/CLI) and are left untouched.
        No-op for code-only indexing or an unset backend.
        """
        backend = self._settings.graphify_llm_backend.strip().lower()
        if self._settings.graphify_code_only or not backend:
            return
        if backend in _GRAPHIFY_OPENAI_SDK_BACKENDS:
            module, extra = "openai", _GRAPHIFY_OPENAI_EXTRA
        else:
            extra = _GRAPHIFY_LLM_EXTRAS.get(backend)
            module = extra
            if not module:
                return
        if _manager._is_module_importable(python, module):
            return
        logger.info(
            "GRAPHIFY_MANAGER: installing graphifyy[{}] into venv for backend {}",
            extra,
            backend,
        )
        proc = await asyncio.create_subprocess_exec(
            _manager._pip_path(python),
            "install",
            "--quiet",
            f"graphifyy[{extra}]",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to install graphifyy[{extra}] for backend {backend}: "
                f"{stderr.decode('utf-8', errors='replace')}"
            )
