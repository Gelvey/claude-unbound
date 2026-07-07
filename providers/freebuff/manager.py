"""Freebuff2API lifecycle manager.

Manages the Freebuff2API subprocess (Docker container or native binary),
health checks, restarts, and model discovery.
"""

from __future__ import annotations

import asyncio
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from .binary_manager import (
    DOCKER_IMAGE,
    binary_path,
    binary_status,
    check_container_running,
    ensure_binary,
)
from .config_generator import (
    config_path,
    generate_config,
    read_config_port,
    write_config,
)
from .credentials import credentials_status, read_auth_tokens

DOCKER_CONTAINER_NAME = "freebuff2api"


class FreebuffManager:
    """Manage a Freebuff2API instance as a child process or Docker container.

    Lifecycle:
        1. :meth:`setup` — ensure binary/image, read credentials, generate config.
        2. :meth:`start` — launch the process/container.
        3. :meth:`health_check` — probe the /healthz endpoint.
        4. :meth:`stop` — gracefully shut down.
        5. :meth:`cleanup` — alias for stop (async context manager support).
    """

    def __init__(
        self,
        *,
        credentials_path: str | Path | None = None,
        port: int | None = None,
        api_keys: list[str] | None = None,
        http_proxy: str = "",
        auto_start: bool = True,
    ):
        self._credentials_path = credentials_path
        self._port = port
        self._api_keys = api_keys
        self._http_proxy = http_proxy
        self._auto_start = auto_start

        # Runtime state.
        self._process: asyncio.subprocess.Process | None = None
        self._docker_container_id: str | None = None
        self._method: str | None = None  # "docker" or "source"
        self._docker_image: str | None = None  # actual Docker image tag from setup
        self._base_url: str | None = None
        self._auth_tokens: list[str] = []
        self._started_at: float | None = None
        self._last_error: str | None = None
        self._models: list[dict[str, Any]] = []
        self._binary_ready: bool = False  # tracks whether ensure_binary already ran

    @property
    def last_error(self) -> str | None:
        """Return the last error message from a failed operation."""
        return self._last_error

    @property
    def base_url(self) -> str | None:
        """Return the base URL of the running Freebuff2API instance."""
        return self._base_url

    @property
    def port(self) -> int | None:
        """Return the port the instance is listening on."""
        return self._port

    @property
    def is_running(self) -> bool:
        """Return whether the process/container is running (based on in-memory state)."""
        if self._method == "docker":
            return self._docker_container_id is not None
        return self._process is not None and self._process.returncode is None

    async def check_actual_status(self) -> dict[str, Any]:
        """Check actual Docker container status by querying Docker daemon.

        This is the authoritative source of truth - queries Docker directly
        instead of relying on in-memory state.
        """
        container_status = await check_container_running()

        # Update method if container is found
        if container_status["container_id"]:
            self._method = "docker"
            if container_status["running"]:
                self._docker_container_id = container_status["container_id"]

        return container_status

    @property
    def method(self) -> str | None:
        """Return the deployment method ("docker" or "source")."""
        return self._method

    @property
    def auth_tokens(self) -> list[str]:
        """Return the loaded auth tokens."""
        return self._auth_tokens

    @property
    def models(self) -> list[dict[str, Any]]:
        """Return the discovered models."""
        return self._models

    async def setup(self, *, skip_binary_ensure: bool = False) -> dict[str, Any]:
        """Set up the Freebuff2API instance.

        1. Ensure binary/image is available (unless *skip_binary_ensure*).
        2. Read auth tokens from credentials.
        3. Generate config file.

        Returns:
            Setup status dict for the admin panel.
        """
        # Ensure binary/image unless already done in this manager's lifetime.
        if skip_binary_ensure and self._method is not None:
            binary_result = binary_status()
            binary_result["available"] = True
            binary_result["method"] = self._method
        else:
            binary_result = await ensure_binary()
            self._binary_ready = binary_result["available"]
        if not binary_result["available"]:
            return {
                "status": "error",
                "error": binary_result["error"],
                "binary": binary_result,
                "credentials": credentials_status(self._credentials_path),
            }
        self._method = binary_result["method"]
        # Only update docker_image if we actually ran ensure_binary (not on skip)
        if not (skip_binary_ensure and self._method is not None):
            self._docker_image = binary_result.get(
                "image"
            )  # Store actual Docker image tag

        # Read auth tokens.
        self._auth_tokens = read_auth_tokens(self._credentials_path)
        if not self._auth_tokens:
            return {
                "status": "error",
                "error": (
                    "No Freebuff auth tokens found.  Run 'npm i -g freebuff && freebuff' "
                    "to login, or set FREEBUFF_CREDENTIALS_PATH to a custom credentials file."
                ),
                "binary": binary_result,
                "credentials": credentials_status(self._credentials_path),
            }

        # Generate config.
        config = generate_config(
            self._auth_tokens,
            port=self._port,
            api_keys=self._api_keys,
            http_proxy=self._http_proxy,
        )
        self._port = int(config["LISTEN_ADDR"].split(":")[-1])
        self._base_url = f"http://127.0.0.1:{self._port}"
        write_config(config, config_path())

        return {
            "status": "ready",
            "method": self._method,
            "port": self._port,
            "base_url": self._base_url,
            "token_count": len(self._auth_tokens),
            "binary": binary_result,
            "credentials": credentials_status(self._credentials_path),
        }

    async def start(self) -> bool:
        """Start the Freebuff2API process/container.

        Returns:
            True if started successfully, False otherwise.
        """
        if self.is_running:
            logger.warning("FREEBUFF_MANAGER: already running")
            return True

        # Run setup to ensure config and credentials are fresh. Skip binary
        # re-ensure if it was already done (avoids 300s Docker pull on every
        # restart).  Call setup() explicitly before start() to force a
        # binary/image refresh.
        setup_result = await self.setup(skip_binary_ensure=self._binary_ready)
        if setup_result["status"] != "ready":
            self._last_error = setup_result.get("error", "Setup failed")
            logger.error(
                "FREEBUFF_MANAGER: setup failed error={}",
                self._last_error,
            )
            return False

        try:
            if self._method == "docker":
                await self._start_docker()
            else:
                await self._start_binary()

            # Wait for the instance to be ready.
            if await self._wait_for_ready():
                self._started_at = time.monotonic()
                self._last_error = None
                logger.info(
                    "FREEBUFF_MANAGER: started method={} port={}",
                    self._method,
                    self._port,
                )
                return True
            else:
                self._last_error = "Container started but health check timed out"
                logger.error("FREEBUFF_MANAGER: failed to become ready")
                await self.stop()
                return False

        except Exception as exc:
            self._last_error = str(exc)
            logger.error("FREEBUFF_MANAGER: start failed error={}", exc)
            return False

    async def _start_docker(self) -> None:
        """Start Freebuff2API as a Docker container."""
        cfg_path = config_path()
        docker_image = self._docker_image or DOCKER_IMAGE
        logger.info(
            "FREEBUFF_MANAGER: starting docker container image={}",
            docker_image,
        )

        # Remove any stale container from a previous crashed run.
        await self._remove_stale_container()

        # Try without sudo first
        docker_cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            DOCKER_CONTAINER_NAME,
            "-p",
            f"{self._port}:{self._port}",
            "-v",
            f"{cfg_path}:/app/config.json:ro,Z",
            docker_image,
            "-config",
            "/app/config.json",
        ]

        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        # Check if permission denied and retry with sudo
        if proc.returncode != 0:
            stderr_text = stderr.decode(errors="replace")
            if "permission denied" in stderr_text.lower() or proc.returncode == 13:
                logger.warning(
                    "FREEBUFF_MANAGER: docker permission denied, retrying with sudo"
                )
                docker_cmd = [
                    "sudo",
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    DOCKER_CONTAINER_NAME,
                    "-p",
                    f"{self._port}:{self._port}",
                    "-v",
                    f"{cfg_path}:/app/config.json:ro,Z",
                    docker_image,
                    "-config",
                    "/app/config.json",
                ]

                proc = await asyncio.create_subprocess_exec(
                    *docker_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"Docker run failed (with sudo): {stderr.decode(errors='replace')}"
                    )
            else:
                raise RuntimeError(f"Docker run failed: {stderr_text}")

        self._docker_container_id = stdout.decode().strip()
        logger.info(
            "FREEBUFF_MANAGER: docker container id={}",
            self._docker_container_id[:12],
        )

    async def _start_binary(self) -> None:
        """Start Freebuff2API as a native binary.

        Uses asyncio subprocess with stdout/stderr redirected to DEVNULL to
        prevent pipe buffer deadlock when the binary produces output that is
        never consumed.
        """
        bin_path = binary_path()
        cfg_path = config_path()
        logger.info("FREEBUFF_MANAGER: starting binary path={}", bin_path)
        self._process = await asyncio.create_subprocess_exec(
            str(bin_path),
            "-config",
            str(cfg_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("FREEBUFF_MANAGER: binary started pid={}", self._process.pid)

    async def _wait_for_ready(self, timeout: float = 30) -> bool:
        """Wait for the Freebuff2API instance to respond to health checks."""
        deadline = time.monotonic() + timeout
        health_url = f"{self._base_url}/healthz"
        logger.info(
            "FREEBUFF_MANAGER: waiting for ready url={} timeout={}", health_url, timeout
        )
        async with httpx.AsyncClient() as client:
            while time.monotonic() < deadline:
                try:
                    resp = await client.get(health_url, timeout=5)
                    logger.debug(
                        "FREEBUFF_MANAGER: health probe status={}", resp.status_code
                    )
                    if resp.status_code == 200:
                        logger.info("FREEBUFF_MANAGER: health check passed")
                        return True
                except httpx.HTTPError as exc:
                    logger.debug("FREEBUFF_MANAGER: health probe error={}", exc)
                await asyncio.sleep(0.5)
        logger.warning("FREEBUFF_MANAGER: health check timed out url={}", health_url)
        return False

    async def stop(self) -> None:
        """Stop the Freebuff2API process/container."""
        # Auto-detect method if not yet known (e.g. fresh singleton).
        if self._method is None:
            container_status = await check_container_running()
            if container_status["running"] and container_status.get("container_id"):
                self._method = "docker"
                self._docker_container_id = container_status["container_id"]

        if self._method == "docker":
            # Find the container by name if we don't have the ID
            container_id = self._docker_container_id
            if not container_id:
                container_status = await check_container_running()
                container_id = container_status.get("container_id")
                if not container_id:
                    logger.warning(
                        "FREEBUFF_MANAGER: no Docker container found to stop"
                    )
                    return

            try:
                # Try without sudo first
                for cmd_prefix in [["docker"], ["sudo", "docker"]]:
                    stop_cmd = [*cmd_prefix, "stop", container_id]
                    proc = await asyncio.create_subprocess_exec(
                        *stop_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.wait()

                    if proc.returncode == 0:
                        # Remove the container
                        rm_cmd = [*cmd_prefix, "rm", container_id]
                        proc = await asyncio.create_subprocess_exec(
                            *rm_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        await proc.wait()
                        break
                    else:
                        stderr = b""
                        if proc.stderr:
                            stderr = await proc.stderr.read()
                        if (
                            "permission denied" in stderr.decode().lower()
                            or proc.returncode == 13
                        ):
                            logger.warning(
                                "FREEBUFF_MANAGER: docker stop permission denied, retrying with sudo"
                            )
                            continue
                        else:
                            logger.warning(
                                "FREEBUFF_MANAGER: docker stop failed stderr={}",
                                stderr.decode(errors="replace"),
                            )
                            break

            except Exception as exc:
                logger.warning("FREEBUFF_MANAGER: docker stop failed error={}", exc)
            self._docker_container_id = None

        elif self._process and self._process.returncode is None:
            try:
                self._process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=10)
                except TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass
            self._process = None

        self._started_at = None
        logger.info("FREEBUFF_MANAGER: stopped")

    async def _remove_stale_container(self) -> None:
        """Remove any stopped freebuff2api container so docker run doesn't fail.

        Only retries with ``sudo`` when the first attempt fails with a
        permission-denied error.  A non-zero exit caused by the container
        not existing is treated as success (nothing to remove).
        """
        for attempt, cmd_prefix in enumerate([["docker"], ["sudo", "docker"]]):
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd_prefix,
                    "rm",
                    "-f",
                    DOCKER_CONTAINER_NAME,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.wait()
            except FileNotFoundError, OSError:
                return

            if proc.returncode == 0:
                return

            # On the first attempt, check for permission denied before
            # falling through to the sudo retry.  Any other failure (e.g.
            # container doesn't exist) means there's nothing to remove.
            if attempt == 0 and proc.stderr:
                stderr_bytes = await proc.stderr.read()
                stderr_text = stderr_bytes.decode(errors="replace").lower()
                if "permission denied" not in stderr_text and proc.returncode != 13:
                    return
            else:
                logger.debug(
                    "FREEBUFF_MANAGER: sudo docker rm failed rc={}",
                    proc.returncode,
                )
                return

    async def restart(self) -> bool:
        """Restart the Freebuff2API instance."""
        await self.stop()
        return await self.start()

    async def health_check(self) -> dict[str, Any]:
        """Probe the /healthz endpoint and return status."""
        if not self._base_url:
            # Auto-detect from running container if possible.
            container_status = await check_container_running()
            if container_status["running"]:
                port = container_status.get("host_port") or read_config_port() or 8080
                self._base_url = f"http://127.0.0.1:{port}"
                logger.info(
                    "FREEBUFF_MANAGER: health_check auto-detected base_url={}",
                    self._base_url,
                )
            else:
                logger.warning("FREEBUFF_MANAGER: health_check no base URL set")
                return {"status": "not_configured", "error": "No base URL set"}

        health_url = f"{self._base_url}/healthz"
        logger.info("FREEBUFF_MANAGER: health_check url={}", health_url)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(health_url, timeout=5)
                logger.debug(
                    "FREEBUFF_MANAGER: health_check status={}", resp.status_code
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "status": "healthy",
                        "uptime_sec": data.get("uptime_sec"),
                        "token_state": data.get("token_state", []),
                    }
                return {
                    "status": "unhealthy",
                    "http_status": resp.status_code,
                }
        except httpx.HTTPError as exc:
            logger.warning(
                "FREEBUFF_MANAGER: health_check unreachable url={} error={}",
                health_url,
                exc,
            )
            return {"status": "unreachable", "error": str(exc)}

    async def discover_models(self) -> list[dict[str, Any]]:
        """Fetch available models from /v1/models."""
        if not self._base_url:
            container_status = await check_container_running()
            if container_status["running"]:
                port = container_status.get("host_port") or read_config_port() or 8080
                self._base_url = f"http://127.0.0.1:{port}"
                logger.info(
                    "FREEBUFF_MANAGER: discover_models auto-detected base_url={}",
                    self._base_url,
                )
            else:
                logger.warning(
                    "FREEBUFF_MANAGER: discover_models no running instance found"
                )
                return []

        models_url = f"{self._base_url}/v1/models"
        logger.info("FREEBUFF_MANAGER: discover_models url={}", models_url)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(models_url, timeout=10)
                logger.debug(
                    "FREEBUFF_MANAGER: discover_models status={}", resp.status_code
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self._models = data.get("data", [])
                    logger.info(
                        "FREEBUFF_MANAGER: discovered models={}",
                        len(self._models),
                    )
                    return self._models
                logger.warning(
                    "FREEBUFF_MANAGER: model discovery failed status={}",
                    resp.status_code,
                )
                return []
        except httpx.HTTPError as exc:
            logger.warning(
                "FREEBUFF_MANAGER: model discovery error={} url={}", exc, models_url
            )
            return []

    def status(self) -> dict[str, Any]:
        """Return in-memory status for the admin panel (fast, no Docker query)."""
        return {
            "running": self.is_running,
            "method": self._method,
            "port": self._port,
            "base_url": self._base_url,
            "started_at": self._started_at,
            "auth_token_count": len(self._auth_tokens),
            "model_count": len(self._models),
            "models": self._models,
            "binary": binary_status(),
            "credentials": credentials_status(self._credentials_path),
        }

    async def get_actual_status(self) -> dict[str, Any]:
        """Return comprehensive status with actual Docker state check.

        This queries Docker directly to get the true running state.
        """
        # Check actual Docker container status (includes host_port from Docker).
        container_status = await self.check_actual_status()

        # Determine the port to use for health checks.
        # Priority: in-memory port → Docker-reported host port → config file → 8080.
        port = self._port
        base_url = self._base_url

        if container_status["running"] and not port:
            port = container_status.get("host_port") or read_config_port() or 8080
            base_url = f"http://127.0.0.1:{port}"

        # Try health check to see if instance is responding
        health_status = "unknown"
        if base_url:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{base_url}/healthz", timeout=2)
                    if resp.status_code == 200:
                        health_status = "healthy"
                    else:
                        health_status = "unhealthy"
            except httpx.HTTPError:
                health_status = "unreachable"

        # If a Docker container is actually running, report docker as the
        # method regardless of in-memory state (source builds don't run in
        # Docker containers).
        effective_method = self._method
        if container_status["container_id"]:
            effective_method = "docker"

        return {
            "running": container_status["running"],
            "method": effective_method,
            "port": port,
            "base_url": base_url,
            "started_at": self._started_at,
            "auth_token_count": len(self._auth_tokens),
            "model_count": len(self._models),
            "models": self._models,
            "binary": binary_status(),
            "credentials": credentials_status(self._credentials_path),
            "container": container_status,
            "health": health_status,
            "requires_sudo": container_status.get("requires_sudo", False),
        }

    async def cleanup(self) -> None:
        """Stop the instance and clean up resources."""
        await self.stop()

    async def __aenter__(self) -> FreebuffManager:
        if self._auto_start:
            await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.cleanup()
