"""Pydantic models for the Graphify project registry."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GraphifyProject(BaseModel):
    """One indexed repository known to Graphify."""

    path: str
    name: str
    graphify_out: str = "graphify-out"
    last_indexed: datetime | None = None
    status: Literal["missing", "indexing", "ready", "stale", "error", "queued"] = (
        "missing"
    )
    error_message: str = ""


class GraphifyProjectRegistry(BaseModel):
    """Root registry of Graphify projects."""

    active_project_path: str | None = None
    projects: list[GraphifyProject] = Field(default_factory=list)
