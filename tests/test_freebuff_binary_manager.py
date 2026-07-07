"""Tests for Freebuff2API binary/image lifecycle helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.freebuff import binary_manager


@pytest.mark.asyncio()
async def test_build_patched_docker_image_reuses_current_patch_image(
    tmp_path: Path,
) -> None:
    patch_file = tmp_path / "freebuff2api.patch"
    patch_file.write_text("current patch", encoding="utf-8")
    patch_hash = binary_manager.hashlib.sha256(patch_file.read_bytes()).hexdigest()
    version = binary_manager._patched_docker_version(patch_hash)

    with (
        patch.object(binary_manager, "_PATCH_FILE", patch_file),
        patch.object(
            binary_manager,
            "_local_image_exists",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch.object(binary_manager, "_read_version", return_value=version),
        patch.object(binary_manager, "_write_version") as write_version,
        patch.object(binary_manager, "_run_cmd", new_callable=AsyncMock) as run_cmd,
    ):
        image = await binary_manager.build_patched_docker_image()

    assert image == binary_manager.DOCKER_IMAGE
    write_version.assert_called_once_with(version)
    run_cmd.assert_not_awaited()


@pytest.mark.asyncio()
async def test_build_patched_docker_image_rebuilds_stale_patch_image(
    tmp_path: Path,
) -> None:
    patch_file = tmp_path / "freebuff2api.patch"
    patch_file.write_text("new patch", encoding="utf-8")

    with (
        patch.object(binary_manager, "_PATCH_FILE", patch_file),
        patch.object(
            binary_manager,
            "_local_image_exists",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch.object(
            binary_manager, "_read_version", return_value="patched-docker-old"
        ),
        patch.object(binary_manager, "_write_version") as write_version,
        patch.object(
            binary_manager,
            "_run_cmd",
            new_callable=AsyncMock,
            return_value=MagicMock(),
        ) as run_cmd,
    ):
        image = await binary_manager.build_patched_docker_image()

    assert image == binary_manager.DOCKER_IMAGE
    commands = [call.args[:3] for call in run_cmd.await_args_list]
    assert ("docker", "build", "-t") in commands
    write_version.assert_called_once()
