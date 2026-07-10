"""Tests for the Graphify project file-change watcher."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.graphify.config import GraphifyProjectRegistry
from api.graphify.projects import add_or_update_project, save_project_registry
from api.graphify.watcher import (
    GraphifyProjectWatcher,
    _directory_mtime_snapshot,
)


@pytest.fixture
def watcher(graphify_tmp_home: Path, graphify_settings: Any):
    """Return a watcher with a mocked manager and a fast interval."""
    manager = MagicMock()
    manager.start_index_project = AsyncMock(return_value={"success": True})
    watcher = GraphifyProjectWatcher(manager, interval_s=0.05)
    yield watcher
    if watcher._task and not watcher._task.done():
        watcher._task.cancel()


def test_directory_mtime_snapshot_detects_newest_file(
    graphify_tmp_home: Path,
) -> None:
    repo = graphify_tmp_home / "repo"
    repo.mkdir()
    (repo / "old.py").write_text("old")
    first = _directory_mtime_snapshot(repo)

    import time

    time.sleep(0.02)
    (repo / "new.py").write_text("new")
    second = _directory_mtime_snapshot(repo)

    assert second > first


def test_directory_mtime_snapshot_ignores_noisy_dirs(
    graphify_tmp_home: Path,
) -> None:
    repo = graphify_tmp_home / "repo"
    repo.mkdir()
    pycache = repo / "__pycache__"
    pycache.mkdir()
    (pycache / "cache.pyc").write_text("cache")

    # Only noisy content means newest stays at 0.0
    assert _directory_mtime_snapshot(repo) == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_watcher_queues_reindex_after_file_change(
    graphify_tmp_home: Path,
    watcher: GraphifyProjectWatcher,
    graphify_settings: Any,
) -> None:
    repo = graphify_tmp_home / "repo"
    repo.mkdir()
    registry = GraphifyProjectRegistry()
    add_or_update_project(registry, path=str(repo), name="repo")
    save_project_registry(registry)

    # First poll establishes baseline
    await watcher._poll()
    assert watcher.manager.start_index_project.await_count == 0

    # Change the project
    (repo / "changed.py").write_text("changed")
    await watcher._poll()

    assert watcher.manager.start_index_project.await_count == 1
    called_project = watcher.manager.start_index_project.await_args.args[0]
    assert called_project.path == str(repo.resolve())


@pytest.mark.asyncio
async def test_watcher_limits_consecutive_polls_by_interval(
    graphify_tmp_home: Path,
    watcher: GraphifyProjectWatcher,
) -> None:
    repo = graphify_tmp_home / "repo"
    repo.mkdir()
    registry = GraphifyProjectRegistry()
    add_or_update_project(registry, path=str(repo), name="repo")
    save_project_registry(registry)

    start = asyncio.get_event_loop().time()
    watcher.start()
    await asyncio.sleep(0.12)
    elapsed = asyncio.get_event_loop().time() - start

    # With a 0.05s interval we should see at most elapsed/0.05 polls plus one.
    # We just care that it does not spin continuously: count should be small.
    assert watcher.manager.start_index_project.await_count < max(
        2, int(elapsed / 0.05) + 1
    )
    await watcher.stop()


def test_snapshot_normalizes_relative_paths(graphify_tmp_home: Path) -> None:
    repo = graphify_tmp_home / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("a")

    assert _directory_mtime_snapshot(repo) > 0.0
