"""Google Vertex AI (OpenAI-compat) adapter."""

from .client import VertexAIProvider
from .endpoint import vertex_openai_base_url

__all__ = ["VertexAIProvider", "vertex_openai_base_url"]
