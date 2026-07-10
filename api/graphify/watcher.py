"""Background watcher that re-indexes Graphify projects when files change."""

from __future__ import annotations

import asyncio
import contextlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

IGNORED_DIR_NAMES = {"graphify-out", ".git", ".venv", "node_modules", "__pycache__"}


def _directory_mtime_snapshot(root: Path, ignore: set[str] | None = None) -> float:
    """Return the newest recursive mtime under *root*, skipping noisy dirs.

    This is intentionally a lightweight poll-based watcher rather than a
    platform-native inotify/fsevents dependency. For large repos the snapshot
    is still bounded by filesystem walk time, so the manager limits how often
    it runs.
    """
    ignore = ignore or IGNORED_DIR_NAMES
    newest = 0.0
    try:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in ignore]
            if (d := Path(dirpath).relative_to(root).parts) and any(
                part in ignore for part in d
            ):
                continue
            for name in filenames:
                file_path = os.path.join(dirpath, name)
                try:
                    mtime = os.path.getmtime(file_path)
                except OSError:
                    continue
                if mtime > newest:
                    newest = mtime
    except OSError:
        pass
    return newest


@dataclass
class GraphifyProjectWatcher:
    """Poll registered projects and trigger background re-indexing on change."""

    manager: Any
    interval_s: float = 60.0
    _snapshots: dict[str, float] = field(default_factory=dict)
    _task: asyncio.Task[Any] | None = field(default=None, init=False)

    def start(self) -> None:
        """Start the background poll task if it is not already running."""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel the background poll task and wait for it to finish."""
        if self._task is None or self._task.done():
            self._task = None
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.interval_s)
                await self._poll()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("GRAPHIFY_WATCHER: poll failed")

    async def _poll(self) -> None:
        from api.graphify.projects import load_project_registry

        registry = load_project_registry()
        for project in registry.projects:
            if project.status not in {"ready", "error", "stale", "missing"}:
                continue
            snapshot = _directory_mtime_snapshot(Path(project.path))
            previous = self._snapshots.get(project.path)
            self._snapshots[project.path] = snapshot
            if previous is None:
                continue
            if abs(snapshot - previous) < 1.0:
                continue
            logger.info(
                "GRAPHIFY_WATCHER: changes detected in {}, queueing re-index",
                project.path,
            )
            await self.manager.start_index_project(project)
