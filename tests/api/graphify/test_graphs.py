"""Tests for graph.json summary reading."""

from __future__ import annotations

import json
from pathlib import Path

from api.graphify.config import GraphifyProject
from api.graphify.graphs import graph_json_path, read_graph_summary


def _write_graph(repo: Path, data: dict) -> None:
    out = repo / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(json.dumps(data))


def test_read_summary_returns_counts_and_file_types(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_graph(
        repo,
        {
            "nodes": [
                {"id": "a", "file_type": "code", "community": 1},
                {"id": "b", "file_type": "code", "community": 1},
                {"id": "c", "file_type": "docs", "community": 2},
            ],
            "links": [{"source": "a", "target": "b"}],
            "hyperedges": [{"id": "h1"}],
            "built_at_commit": "0ba13d8e4938",
        },
    )

    project = GraphifyProject(path=str(repo), name="repo")
    summary = read_graph_summary(project)

    assert summary["present"] is True
    assert summary["node_count"] == 3
    assert summary["link_count"] == 1
    assert summary["hyperedge_count"] == 1
    assert summary["communities"] == 2
    assert summary["file_types"] == {"code": 2, "docs": 1}
    assert summary["built_at_commit"] == "0ba13d8e4938"


def test_read_summary_not_indexed_when_absent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    project = GraphifyProject(path=str(repo), name="repo")
    summary = read_graph_summary(project)
    assert summary["present"] is False
    assert summary["reason"] == "not_indexed"


def test_read_summary_unreadable_on_bad_json(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "graphify-out").mkdir(parents=True)
    (repo / "graphify-out" / "graph.json").write_text("{ not json")
    project = GraphifyProject(path=str(repo), name="repo")
    summary = read_graph_summary(project)
    assert summary["present"] is False
    assert summary["reason"] == "unreadable"


def test_graph_json_path_uses_graphify_out(tmp_path: Path) -> None:
    project = GraphifyProject(
        path=str(tmp_path), name="repo", graphify_out="custom-out"
    )
    assert graph_json_path(project) == tmp_path / "custom-out" / "graph.json"
