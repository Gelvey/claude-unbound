"""Vertex AI service and OpenAI-compatible endpoint construction."""

from __future__ import annotations

import re

from config.provider_catalog import VERTEX_AI_DEFAULT_BASE

_LOCATION_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _validated_location(location: str) -> str:
    normalized = location.strip().lower()
    if not normalized:
        raise ValueError(
            "VERTEX_AI_LOCATION is not set. Use 'global' or a Google Cloud region."
        )
    if _LOCATION_PATTERN.fullmatch(normalized) is None:
        raise ValueError(
            "VERTEX_AI_LOCATION must be 'global' or a lowercase Google Cloud region."
        )
    return normalized


def vertex_service_endpoint(location: str) -> str:
    """Return Google's global or regional Vertex AI service endpoint."""
    normalized = _validated_location(location)
    if normalized == "global":
        return VERTEX_AI_DEFAULT_BASE
    return f"https://{normalized}-aiplatform.googleapis.com"


def vertex_openai_base_url(project_id: str, location: str = "global") -> str:
    """Return the project-scoped Vertex OpenAI-compatible API base URL."""
    project = project_id.strip()
    if not project:
        raise ValueError("VERTEX_AI_PROJECT_ID is not set. Add it to your .env file.")
    normalized_location = _validated_location(location)
    service_endpoint = vertex_service_endpoint(normalized_location)
    return (
        f"{service_endpoint}/v1/projects/{project}/locations/"
        f"{normalized_location}/endpoints/openapi"
    )


def vertex_publisher_models_url(location: str = "global") -> str:
    """Return Google's native publisher-model listing endpoint."""
    return f"{vertex_service_endpoint(location)}/v1beta1/publishers/google/models"
