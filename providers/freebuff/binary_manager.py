"""Manage Freebuff2API binary lifecycle.

Freebuff2API is distributed as Docker images on GHCR
(``ghcr.io/gelvey/freebuff2api:latest``).  This module handles:

1. **Docker** (primary): Pull and run the container.
2. **Go build** (fallback): Build from source if Go is installed.
3. **Version tracking**: Cache the current version to avoid redundant pulls.

The binary/container lives in ``~/.fcc/freebuff2api/``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import shutil
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

# Upstream Docker image (only used when no local patch is present).
_UPSTREAM_DOCKER_IMAGE = "ghcr.io/gelvey/freebuff2api:latest"

# Local patched Docker image tag (built from patched source).
DOCKER_IMAGE = "fcc/freebuff2api:latest"

# Local directory for Freebuff2API artifacts.
_INSTALL_DIR = Path.home() / ".fcc" / "freebuff2api"

# Version tracking file.
_VERSION_FILE = _INSTALL_DIR / "version.json"

# GitHub source repo for Go build fallback.
_SOURCE_REPO = "https://github.com/Gelvey/Freebuff2API.git"

# Patch applied to the upstream code before building.
_PATCH_FILE = Path(__file__).with_name("freebuff2api.patch")


def install_dir() -> Path:
    """Return the Freebuff2API install directory."""
    return _INSTALL_DIR


def binary_path() -> Path:
    """Return the path to the Freebuff2API binary (if built from source)."""
    name = "Freebuff2API.exe" if platform.system() == "Windows" else "Freebuff2API"
    return _INSTALL_DIR / name


def _read_version() -> str | None:
    """Read the cached version string, or None if not tracked."""
    if not _VERSION_FILE.is_file():
        return None
    try:
        data = json.loads(_VERSION_FILE.read_text(encoding="utf-8"))
        return data.get("version")
    except OSError, json.JSONDecodeError:
        return None


def _write_version(version: str) -> None:
    """Write the version tracking file."""
    _INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    _VERSION_FILE.write_text(
        json.dumps({"version": version}, indent=2),
        encoding="utf-8",
    )


def _patch_hash() -> str:
    """Return a stable hash for the bundled patch, or ``"none"`` if absent."""
    if not _PATCH_FILE.is_file():
        return "none"
    return hashlib.sha256(_PATCH_FILE.read_bytes()).hexdigest()


def _patched_docker_version(patch_hash: str) -> str:
    """Return the cache version string for a patched Docker image."""
    return f"patched-docker-{patch_hash[:8]}"


async def _apply_patch(source_dir: str | Path) -> None:
    """Apply :data:`_PATCH_FILE` to a cloned source directory."""
    if not _PATCH_FILE.is_file():
        return
    patch_path = _PATCH_FILE.resolve()
    await _run_cmd(
        "git",
        "-C",
        str(source_dir),
        "apply",
        "--check",
        str(patch_path),
        timeout=30,
    )
    await _run_cmd(
        "git",
        "-C",
        str(source_dir),
        "apply",
        str(patch_path),
        timeout=30,
    )
    logger.info("FREEBUFF_BINARY: applied patch {}", _PATCH_FILE.name)


async def _run_cmd(
    *args: str,
    check: bool = True,
    timeout: float = 300,
    cwd: str | Path | None = None,
) -> asyncio.subprocess.Process:
    """Run a subprocess command and return the process."""
    logger.debug("FREEBUFF_BINARY: running cmd={}", " ".join(args))
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        raise
    if check and proc.returncode != 0:
        stderr = b""
        if proc.stderr:
            stderr = await proc.stderr.read()
        raise RuntimeError(
            f"Command failed (rc={proc.returncode}): {' '.join(args)}\n"
            f"{stderr.decode(errors='replace')}"
        )
    return proc


async def check_docker_available() -> bool:
    """Check if Docker is installed and running."""
    try:
        proc = await _run_cmd("docker", "info", check=False, timeout=10)
        return proc.returncode == 0
    except FileNotFoundError, TimeoutError, OSError:
        return False


async def check_go_available() -> bool:
    """Check if Go is installed."""
    try:
        proc = await _run_cmd("go", "version", check=False, timeout=10)
        return proc.returncode == 0
    except FileNotFoundError, TimeoutError, OSError:
        return False


async def pull_docker_image(image_tag: str = _UPSTREAM_DOCKER_IMAGE) -> str:
    """Pull an upstream Docker image.  Returns the image tag."""
    logger.info("FREEBUFF_BINARY: pulling docker image={}", image_tag)
    await _run_cmd("docker", "pull", image_tag, timeout=300)
    _write_version("docker-latest")
    logger.info("FREEBUFF_BINARY: docker pull complete")
    return image_tag


async def build_from_source() -> Path:
    """Build Freebuff2API from source using Go.  Returns the binary path."""
    _INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    bin_path = binary_path()
    patch_hash = _patch_hash()
    version = f"patched-source-{patch_hash[:8]}"

    if bin_path.exists() and _read_version() == version:
        logger.info("FREEBUFF_BINARY: cached binary is up to date")
        return bin_path

    with tempfile.TemporaryDirectory(prefix="freebuff-build-") as tmpdir:
        logger.info("FREEBUFF_BINARY: cloning source repo={}", _SOURCE_REPO)
        await _run_cmd("git", "clone", "--depth=1", _SOURCE_REPO, tmpdir, timeout=120)
        await _apply_patch(tmpdir)

        logger.info("FREEBUFF_BINARY: building binary")
        goos = "linux"
        goarch = "amd64"
        system = platform.system().lower()
        machine = platform.machine().lower()
        if system == "darwin":
            goos = "darwin"
        elif system == "windows":
            goos = "windows"
        if machine in ("arm64", "aarch64"):
            goarch = "arm64"

        env_vars = {
            "CGO_ENABLED": "0",
            "GOOS": goos,
            "GOARCH": goarch,
        }

        proc = await asyncio.create_subprocess_exec(
            "go",
            "build",
            "-ldflags=-s -w",
            "-trimpath",
            "-o",
            str(bin_path),
            ".",
            cwd=tmpdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**dict(__import__("os").environ), **env_vars},
        )
        await asyncio.wait_for(proc.wait(), timeout=600)
        if proc.returncode != 0:
            stderr = b""
            if proc.stderr:
                stderr = await proc.stderr.read()
            raise RuntimeError(
                f"Go build failed (rc={proc.returncode}): "
                f"{stderr.decode(errors='replace')}"
            )

    _write_version(version)
    logger.info("FREEBUFF_BINARY: build complete path={}", bin_path)
    return bin_path


async def _local_image_exists(image_tag: str) -> bool:
    """Return whether a Docker image tag exists locally."""
    try:
        proc = await _run_cmd(
            "docker", "images", "-q", image_tag, check=False, timeout=10
        )
        output = (await proc.stdout.read()).decode().strip() if proc.stdout else ""
        return proc.returncode == 0 and output != ""
    except FileNotFoundError, TimeoutError, OSError:
        return False


async def build_patched_docker_image() -> str:
    """Build a patched Docker image from source.  Returns the image tag."""
    patch_hash = _patch_hash()
    image_tag = DOCKER_IMAGE
    version = _patched_docker_version(patch_hash)

    if not _PATCH_FILE.is_file():
        return await pull_docker_image(_UPSTREAM_DOCKER_IMAGE)

    if await _local_image_exists(image_tag) and _read_version() == version:
        logger.info("FREEBUFF_BINARY: patched Docker image already exists")
        _write_version(version)
        return image_tag

    with tempfile.TemporaryDirectory(prefix="freebuff-docker-build-") as tmpdir:
        logger.info("FREEBUFF_BINARY: cloning source repo for patched Docker build")
        await _run_cmd("git", "clone", "--depth=1", _SOURCE_REPO, tmpdir, timeout=120)
        await _apply_patch(tmpdir)
        logger.info("FREEBUFF_BINARY: building patched Docker image tag={}", image_tag)
        await _run_cmd("docker", "build", "-t", image_tag, ".", cwd=tmpdir, timeout=600)

    _write_version(version)
    logger.info("FREEBUFF_BINARY: patched Docker image ready")
    return image_tag


async def ensure_binary() -> dict[str, Any]:
    """Ensure the Freebuff2API binary/image is available.

    Tries Docker first (primary), then Go build (fallback).

    Returns:
        Dict with ``method`` ("docker" or "source"), ``available`` (bool),
        ``path`` (str, for source builds), ``image`` (str, for Docker),
        and ``error`` (str, if failed).
    """
    # Prefer a patched Docker image built from source.
    if await check_docker_available():
        try:
            image = await build_patched_docker_image()
            return {
                "method": "docker",
                "available": True,
                "image": image,
                "path": None,
                "error": None,
            }
        except Exception as exc:
            logger.warning(
                "FREEBUFF_BINARY: patched docker build failed, trying Go build error={}",
                exc,
            )

    # Fallback: patched Go build from source.
    if await check_go_available():
        try:
            path = await build_from_source()
            return {
                "method": "source",
                "available": True,
                "image": None,
                "path": str(path),
                "error": None,
            }
        except Exception as exc:
            logger.error("FREEBUFF_BINARY: go build failed error={}", exc)
            return {
                "method": "source",
                "available": False,
                "image": None,
                "path": None,
                "error": str(exc),
            }

    return {
        "method": None,
        "available": False,
        "image": None,
        "path": None,
        "error": (
            "Neither Docker nor Go is available.  Install Docker "
            "(https://docs.docker.com/get-docker/) or Go (https://go.dev/dl/) "
            "to use the Freebuff provider."
        ),
    }


def binary_status() -> dict[str, Any]:
    """Return current binary status for the admin panel."""
    has_docker = shutil.which("docker") is not None
    has_go = shutil.which("go") is not None
    has_binary = binary_path().is_file()
    version = _read_version()

    method = None
    if has_binary:
        method = "source"
    elif has_docker:
        method = "docker"

    return {
        "method": method,
        "docker_available": has_docker,
        "go_available": has_go,
        "binary_exists": has_binary,
        "binary_path": str(binary_path()) if has_binary else None,
        "version": version,
    }


def _extract_host_port(inspect_output: str) -> int | None:
    """Extract the first host port from docker inspect port-binding output.

    Port binding output comes as ``<containerPort>/<proto>-><hostPort>`` pairs
    separated by commas (e.g. ``8080/tcp->38447,``).
    Returns the first *host* port as an int, or ``None`` if unparseable.
    """
    for segment in inspect_output.split(","):
        # Expect e.g. "8080/tcp->38447"
        if "->" in segment:
            host_part = segment.split("->")[-1].strip()
            if host_part:
                try:
                    return int(host_part)
                except ValueError:
                    pass
    return None


# Go template passed to ``docker inspect --format``.
# Outputs ``containerId|Status|Running|<containerPort>/<proto>-><hostPort>,``
# The final field is empty when no port bindings exist (stopped / --net=none).
_INSPECT_FMT = (
    "{{.Id}}|{{.State.Status}}|{{.State.Running}}"
    "|{{range $p, $conf := .HostConfig.PortBindings}}"
    "{{$p}}->{{(index $conf 0).HostPort}},{{end}}"
)


def _parse_inspect(output: str) -> dict[str, Any] | None:
    """Parse the pipe-delimited output of ``docker inspect --format _INSPECT_FMT``.

    Returns a dict with ``container_id``, ``status``, ``running``,
    and ``host_port`` (int or None), or ``None`` if the output cannot be parsed.
    """
    parts = output.strip().split("|")
    # The last segment may contain the port-bindings blob.
    if len(parts) < 4:
        return None
    container_id, status, running, raw_ports = parts[0], parts[1], parts[2], parts[3]
    return {
        "container_id": container_id,
        "status": status,
        "running": running.lower() == "true" and status == "running",
        "host_port": _extract_host_port(raw_ports),
    }


async def _inspect_container(
    *prefix: str,
) -> tuple[dict[str, Any] | None, bool]:
    """Run ``docker inspect`` on the freebuff2api container.

    *prefix* is prepended to the command (e.g. ``["sudo"]``).

    Returns ``(parsed, needs_sudo_retry)``:
      - *parsed*: dict with ``container_id``, ``status``, ``running``,
        ``host_port`` — or ``None`` on failure / not-found.
      - *needs_sudo_retry*: ``True`` when the command failed with a
        permission error and the caller should retry with ``["sudo"]``.
    """
    try:
        proc = await _run_cmd(
            *prefix,
            "docker",
            "inspect",
            "--format",
            _INSPECT_FMT,
            "freebuff2api",
            check=False,
            timeout=10,
        )
        if proc.returncode == 0:
            stdout = (await proc.stdout.read()).decode().strip() if proc.stdout else ""
            logger.debug(
                "FREEBUFF_BINARY: docker inspect stdout={}",
                stdout.replace("\n", " ")[:200],
            )
            return _parse_inspect(stdout), False

        stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
        logger.debug("FREEBUFF_BINARY: docker inspect failed stderr={}", stderr.strip())
        # Permission denied — caller should retry with sudo.
        if "permission denied" in stderr.lower() or proc.returncode == 13:
            return None, True
        return None, False
    except FileNotFoundError, TimeoutError, OSError:
        return None, False


async def check_container_running() -> dict[str, Any]:
    """Check if the freebuff2api Docker container is running.

    Returns:
        Dict with container status information:
        - running: bool - whether container is running
        - container_id: str | None - container ID if exists
        - status: str - "running", "exited", "not_found", "error"
        - host_port: int | None - host port mapped into the container
        - error: str | None - error message if failed
        - requires_sudo: bool - whether sudo was needed
    """
    result: dict[str, Any] = {
        "running": False,
        "container_id": None,
        "status": "not_found",
        "host_port": None,
        "error": None,
        "requires_sudo": False,
    }

    if not shutil.which("docker"):
        result["status"] = "error"
        result["error"] = "Docker not available"
        logger.debug("FREEBUFF_BINARY: docker binary not found on PATH")
        return result

    parsed, needs_sudo = await _inspect_container()
    if needs_sudo:
        logger.debug(
            "FREEBUFF_BINARY: docker inspect permission denied, retrying with sudo"
        )
        result["requires_sudo"] = True
        parsed, _ = await _inspect_container("sudo")
    if parsed:
        result.update(
            container_id=parsed["container_id"],
            status=parsed["status"],
            running=parsed["running"],
            host_port=parsed["host_port"],
        )

    logger.debug("FREEBUFF_BINARY: container_running status={}", result)
    return result
