"""API request pipeline for routing, intercepts, and provider execution."""

from __future__ import annotations

import contextlib
import traceback
import uuid
from collections.abc import AsyncIterator, Callable, Iterable
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from api.graphify.mcp_proxy import GRAPHIFY_TOOL_NAMES
from config.provider_catalog import PROVIDER_CATALOG
from config.settings import Settings
from core.anthropic import get_token_count, get_user_facing_error_message
from core.anthropic.sse import ANTHROPIC_SSE_RESPONSE_HEADERS
from core.anthropic.system_directive import append_system_directive
from core.openai_responses import OpenAIResponsesAdapter
from core.trace import api_messages_request_snapshot, trace_event, traced_async_stream
from providers.base import BaseProvider
from providers.exceptions import InvalidRequestError, ProviderError

from .model_router import ModelRouter, RoutedMessagesRequest
from .models.anthropic import MessagesRequest, TokenCountRequest
from .models.openai_responses import OpenAIResponsesRequest
from .models.responses import TokenCountResponse
from .optimization_handlers import try_optimizations
from .web_tools.egress import WebFetchEgressPolicy
from .web_tools.request import (
    is_web_server_tool_request,
    openai_chat_upstream_server_tool_error,
)
from .web_tools.streaming import stream_web_server_tool_response

TokenCounter = Callable[[list[Any], str | list[Any] | None, list[Any] | None], int]
ProviderGetter = Callable[[str], BaseProvider]
MessageIntercept = Callable[[RoutedMessagesRequest], object | None]
RerouteStrategy = Callable[
    [RoutedMessagesRequest, Settings], RoutedMessagesRequest | None
]

# Providers that use ``/chat/completions`` + Anthropic-to-OpenAI conversion.
_OPENAI_CHAT_UPSTREAM_IDS = frozenset(
    provider_id
    for provider_id, descriptor in PROVIDER_CATALOG.items()
    if descriptor.transport_type == "openai_chat"
)


def anthropic_sse_streaming_response(body: AsyncIterator[str]) -> StreamingResponse:
    """Return a streaming response for Anthropic-style SSE streams."""
    return StreamingResponse(
        body,
        media_type="text/event-stream",
        headers=ANTHROPIC_SSE_RESPONSE_HEADERS,
    )


def openai_responses_sse_streaming_response(
    body: AsyncIterator[str],
) -> StreamingResponse:
    """Return a streaming response for OpenAI Responses-style SSE."""
    return StreamingResponse(
        body,
        media_type="text/event-stream",
        headers=OpenAIResponsesAdapter.sse_headers,
    )


def _http_status_for_unexpected_pipeline_exception(_exc: BaseException) -> int:
    """HTTP status for uncaught non-provider failures."""
    return 500


def _log_unexpected_pipeline_exception(
    settings: Settings,
    exc: BaseException,
    *,
    context: str,
    request_id: str | None = None,
) -> None:
    """Log API failures without echoing exception text unless opted in."""
    if settings.log_api_error_tracebacks:
        if request_id is not None:
            logger.error("{} request_id={}: {}", context, request_id, exc)
        else:
            logger.error("{}: {}", context, exc)
        logger.error(traceback.format_exc())
        return
    if request_id is not None:
        logger.error(
            "{} request_id={} exc_type={}",
            context,
            request_id,
            type(exc).__name__,
        )
    else:
        logger.error("{} exc_type={}", context, type(exc).__name__)


def _require_non_empty_messages(messages: list[Any]) -> None:
    if not messages:
        raise InvalidRequestError("messages cannot be empty")


# Module-level mutable list so custom modules can contribute intercepts.
_MESSAGE_INTERCEPTS: list[MessageIntercept] = []
# Module-level mutable list so custom modules can contribute reroute strategies.
_REROUTE_STRATEGIES: list[RerouteStrategy] = []
# Module-level override slot; non-None value replaces ``get_token_count``.
_MODULE_TOKEN_COUNTER: TokenCounter | None = None
# Module-level system-prompt directives applied to every MessagesRequest.
_MODULE_SYSTEM_DIRECTIVES: list[str] = []


def _graphify_project_directive(project_path: str, tool_names: list[str]) -> str:
    """Return a system directive that tells the model the current repo root."""
    tools = ", ".join(tool_names)
    return (
        f"The current project root for Graphify is: {project_path}. "
        f"When calling any Graphify tool ({tools}), "
        f"always include project_path={project_path!r} in the tool arguments."
    )


def add_message_intercepts(
    intercepts: Iterable[MessageIntercept],
) -> None:
    """Append intercepts to the runtime message-intercept list."""

    _MESSAGE_INTERCEPTS.extend(intercepts)


def remove_message_intercepts(intercepts: Iterable[MessageIntercept]) -> None:
    """Remove previously appended intercepts (used by tests)."""

    for intercept in intercepts:
        with contextlib.suppress(ValueError):
            _MESSAGE_INTERCEPTS.remove(intercept)


def add_reroute_strategies(strategies: Iterable[RerouteStrategy]) -> None:
    """Append reroute strategies (run after model resolve, before long-context fallback)."""

    _REROUTE_STRATEGIES.extend(strategies)


def remove_reroute_strategies(strategies: Iterable[RerouteStrategy]) -> None:
    """Remove previously appended reroute strategies (used by tests)."""

    for strategy in strategies:
        with contextlib.suppress(ValueError):
            _REROUTE_STRATEGIES.remove(strategy)


def get_reroute_strategies() -> list[RerouteStrategy]:
    """Return a copy of the registered reroute strategies."""

    return list(_REROUTE_STRATEGIES)


def set_module_token_counter(counter: TokenCounter | None) -> None:
    """Override the request token counter (last-registered wins)."""

    global _MODULE_TOKEN_COUNTER
    _MODULE_TOKEN_COUNTER = counter


def reset_module_token_counter() -> None:
    """Clear the module-supplied token counter (used by tests)."""

    set_module_token_counter(None)


def get_module_token_counter() -> TokenCounter | None:
    """Return the module-supplied token counter, or None if none registered."""

    return _MODULE_TOKEN_COUNTER


def set_module_system_directives(directives: list[str]) -> None:
    """Replace the module-supplied system directives."""

    global _MODULE_SYSTEM_DIRECTIVES
    _MODULE_SYSTEM_DIRECTIVES = list(directives)


def get_module_system_directives() -> list[str]:
    """Return a copy of the module-supplied system directives."""

    return list(_MODULE_SYSTEM_DIRECTIVES)


class ApiRequestPipeline:
    """Coordinate API request intercepts, routing, and provider stream execution."""

    def __init__(
        self,
        settings: Settings,
        provider_getter: ProviderGetter,
        model_router: ModelRouter | None = None,
        token_counter: TokenCounter | None = None,
        responses_adapter: OpenAIResponsesAdapter | None = None,
        *,
        graphify_project_path: str | None = None,
    ) -> None:
        self._settings = settings
        self._provider_getter = provider_getter
        self._model_router = model_router or ModelRouter(settings)
        self._responses_adapter = responses_adapter or OpenAIResponsesAdapter()
        self._graphify_project_path = graphify_project_path
        # Module-supplied token counter takes precedence over the default;
        # explicit constructor argument still wins over both for tests.
        module_token_counter = get_module_token_counter()
        self._token_counter: TokenCounter = (
            token_counter or module_token_counter or get_token_count
        )
        # Start with the built-in intercepts, then any intercepts contributed by
        # custom modules. This is a copy so per-instance mutation is isolated.
        self._message_intercepts: list[MessageIntercept] = [
            self._intercept_web_server_tool,
            self._intercept_local_optimization,
            *_MESSAGE_INTERCEPTS,
        ]

    def create_message(self, request_data: MessagesRequest) -> object:
        """Create an Anthropic-compatible message response."""
        try:
            _require_non_empty_messages(request_data.messages)
            routed = self._model_router.resolve_messages_request(request_data)
            routed = self._apply_module_reroutes(routed)
            routed = self._maybe_reroute_long_context(routed)
            self._reject_unsupported_server_tools(routed)

            intercepted = self._run_message_intercepts(routed)
            if intercepted is not None:
                return intercepted

            logger.debug("No optimization matched, routing to provider")
            return anthropic_sse_streaming_response(
                self._provider_stream(
                    routed,
                    wire_api="messages",
                    raw_log_label="FULL_PAYLOAD",
                    raw_log_payload=routed.request.model_dump,
                )
            )
        except ProviderError:
            raise
        except Exception as e:
            _log_unexpected_pipeline_exception(
                self._settings, e, context="CREATE_MESSAGE_ERROR"
            )
            raise HTTPException(
                status_code=_http_status_for_unexpected_pipeline_exception(e),
                detail=get_user_facing_error_message(e),
            ) from e

    async def create_response(self, request_data: OpenAIResponsesRequest) -> object:
        """Create a streaming OpenAI Responses-compatible response."""
        request_payload = request_data.model_dump(mode="json", exclude_none=True)
        if request_data.stream is False:
            invalid_request = InvalidRequestError(
                "Claude Unbound /v1/responses supports streaming only; omit stream or set stream=true."
            )
            return JSONResponse(
                status_code=invalid_request.status_code,
                content=self._responses_adapter.error_payload(
                    message=invalid_request.message,
                    error_type=invalid_request.error_type,
                ),
            )

        try:
            anthropic_payload = self._responses_adapter.to_anthropic_payload(
                request_payload
            )
            response_request = MessagesRequest(**anthropic_payload)
            _require_non_empty_messages(response_request.messages)
            routed = self._model_router.resolve_messages_request(response_request)
            routed = self._apply_module_reroutes(routed)
            routed = self._maybe_reroute_long_context(routed)
            self._reject_unsupported_server_tools(routed)

            streamed = self._provider_stream(
                routed,
                wire_api="responses",
                raw_log_label="FULL_RESPONSES_PAYLOAD",
                raw_log_payload=lambda: request_payload,
            )
            return openai_responses_sse_streaming_response(
                self._responses_adapter.iter_sse_from_anthropic(
                    streamed,
                    request_payload,
                )
            )
        except OpenAIResponsesAdapter.ConversionError as exc:
            invalid_request = InvalidRequestError(str(exc))
            return JSONResponse(
                status_code=invalid_request.status_code,
                content=self._responses_adapter.error_payload(
                    message=invalid_request.message,
                    error_type=invalid_request.error_type,
                ),
            )
        except ProviderError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=self._responses_adapter.error_payload(
                    message=exc.message,
                    error_type=exc.error_type,
                ),
            )
        except Exception as e:
            _log_unexpected_pipeline_exception(
                self._settings,
                e,
                context="CREATE_RESPONSE_ERROR",
            )
            return JSONResponse(
                status_code=_http_status_for_unexpected_pipeline_exception(e),
                content=self._responses_adapter.error_payload(
                    message=get_user_facing_error_message(e),
                    error_type="api_error",
                ),
            )

    def count_tokens(self, request_data: TokenCountRequest) -> TokenCountResponse:
        """Count tokens for a request after applying configured model routing."""
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        with logger.contextualize(request_id=request_id):
            try:
                _require_non_empty_messages(request_data.messages)
                routed = self._model_router.resolve_token_count_request(request_data)
                raw_tokens = self._token_counter(
                    routed.request.messages, routed.request.system, routed.request.tools
                )
                # Correct tiktoken's undercount vs the Anthropic tokenizer so
                # client context management (auto-compaction) fires on time.
                # Applied only to this endpoint, not to streamed usage metrics.
                tokens = max(1, int(raw_tokens * self._settings.token_count_multiplier))
                trace_event(
                    stage="routing",
                    event="api.route.resolved",
                    source="api",
                    kind="count_tokens",
                    provider_id=routed.resolved.provider_id,
                    provider_model=routed.resolved.provider_model,
                    provider_model_ref=routed.resolved.provider_model_ref,
                    gateway_model=routed.request.model,
                )
                trace_event(
                    stage="ingress",
                    event="api.count_tokens.completed",
                    source="api",
                    message_count=len(routed.request.messages),
                    input_tokens=tokens,
                    snapshot=api_messages_request_snapshot(routed.request),
                )
                return TokenCountResponse(input_tokens=tokens)
            except ProviderError:
                raise
            except Exception as e:
                _log_unexpected_pipeline_exception(
                    self._settings,
                    e,
                    context="COUNT_TOKENS_ERROR",
                    request_id=request_id,
                )
                raise HTTPException(
                    status_code=_http_status_for_unexpected_pipeline_exception(e),
                    detail=get_user_facing_error_message(e),
                ) from e

    def _maybe_reroute_long_context(
        self, routed: RoutedMessagesRequest
    ) -> RoutedMessagesRequest:
        """Reroute oversized requests to the configured long-context fallback model.

        Enabled only when both ``LONG_CONTEXT_MODEL`` and
        ``LONG_CONTEXT_THRESHOLD_TOKENS`` are set. Uses the raw local token
        estimate (no multiplier).
        """
        fallback_ref = self._settings.long_context_model
        threshold = self._settings.long_context_threshold_tokens
        if not fallback_ref or threshold <= 0:
            return routed
        if routed.resolved.provider_model_ref == fallback_ref:
            return routed

        estimated_tokens = self._token_counter(
            routed.request.messages, routed.request.system, routed.request.tools
        )
        if estimated_tokens <= threshold:
            return routed

        resolved = self._model_router.resolve(fallback_ref)
        routed.request.model = resolved.provider_model
        trace_event(
            stage="routing",
            event="api.route.long_context_fallback",
            source="api",
            estimated_tokens=estimated_tokens,
            threshold_tokens=threshold,
            from_provider_model_ref=routed.resolved.provider_model_ref,
            to_provider_model_ref=fallback_ref,
        )
        logger.info(
            "LONG_CONTEXT_FALLBACK: estimated_tokens={} > threshold={} rerouting "
            "'{}' -> '{}'",
            estimated_tokens,
            threshold,
            routed.resolved.provider_model_ref,
            fallback_ref,
        )
        return RoutedMessagesRequest(request=routed.request, resolved=resolved)

    def _apply_module_reroutes(
        self, routed: RoutedMessagesRequest
    ) -> RoutedMessagesRequest:
        """Run module-supplied reroute strategies in registration order.

        Each strategy may return a rewritten :class:`RoutedMessagesRequest`
        or ``None`` to leave the request unchanged. The first non-None
        result wins; later strategies still run against the rewritten
        request, so modules can compose.
        """

        for strategy in get_reroute_strategies():
            try:
                rewritten = strategy(routed, self._settings)
            except Exception as exc:
                _log_unexpected_pipeline_exception(
                    self._settings,
                    exc,
                    context="MODULE_REROUTE_ERROR",
                )
                continue
            if rewritten is not None:
                routed = rewritten
        return routed

    def _reject_unsupported_server_tools(self, routed: RoutedMessagesRequest) -> None:
        if routed.resolved.provider_id not in _OPENAI_CHAT_UPSTREAM_IDS:
            return
        tool_err = openai_chat_upstream_server_tool_error(
            routed.request,
            web_tools_enabled=self._settings.enable_web_server_tools,
        )
        if tool_err is not None:
            raise InvalidRequestError(tool_err)

    def _run_message_intercepts(self, routed: RoutedMessagesRequest) -> object | None:
        for intercept in self._message_intercepts:
            result = intercept(routed)
            if result is not None:
                return result
        return None

    def _intercept_web_server_tool(
        self, routed: RoutedMessagesRequest
    ) -> object | None:
        if not self._settings.enable_web_server_tools:
            return None
        if not is_web_server_tool_request(routed.request):
            return None

        input_tokens = self._token_counter(
            routed.request.messages, routed.request.system, routed.request.tools
        )
        trace_event(
            stage="routing",
            event="api.optimization.web_server_tool",
            source="api",
            model=routed.request.model,
        )
        egress = WebFetchEgressPolicy(
            allow_private_network_targets=self._settings.web_fetch_allow_private_networks,
            allowed_schemes=self._settings.web_fetch_allowed_scheme_set(),
        )
        return anthropic_sse_streaming_response(
            stream_web_server_tool_response(
                routed.request,
                input_tokens=input_tokens,
                web_fetch_egress=egress,
                verbose_client_errors=self._settings.log_api_error_tracebacks,
            ),
        )

    def _intercept_local_optimization(
        self, routed: RoutedMessagesRequest
    ) -> object | None:
        optimized = try_optimizations(routed.request, self._settings)
        if optimized is None:
            return None
        trace_event(
            stage="routing",
            event="api.optimization.short_circuit",
            source="api",
            model=routed.request.model,
        )
        return optimized

    def _provider_stream(
        self,
        routed: RoutedMessagesRequest,
        *,
        wire_api: str,
        raw_log_label: str,
        raw_log_payload: Callable[[], Any],
    ) -> AsyncIterator[str]:
        if self._settings.concise_output:
            append_system_directive(
                routed.request, self._settings.concise_output_directive
            )
        if self._graphify_project_path:
            append_system_directive(
                routed.request,
                _graphify_project_directive(
                    self._graphify_project_path, sorted(GRAPHIFY_TOOL_NAMES)
                ),
            )
        for directive in get_module_system_directives():
            append_system_directive(routed.request, directive)

        provider = self._provider_getter(routed.resolved.provider_id)
        provider.preflight_stream(
            routed.request,
            thinking_enabled=routed.resolved.thinking_enabled,
        )

        route_trace: dict[str, Any] = {
            "stage": "routing",
            "event": "api.route.resolved",
            "source": "api",
            "provider_id": routed.resolved.provider_id,
            "provider_model": routed.resolved.provider_model,
            "provider_model_ref": routed.resolved.provider_model_ref,
            "gateway_model": routed.request.model,
            "thinking_enabled": routed.resolved.thinking_enabled,
        }
        if wire_api == "responses":
            route_trace["wire_api"] = "responses"
        trace_event(**route_trace)

        request_id = f"req_{uuid.uuid4().hex[:12]}"
        trace_event(
            stage="ingress",
            event=(
                "api.responses.request.received"
                if wire_api == "responses"
                else "api.request.received"
            ),
            source="api",
            message_count=len(routed.request.messages),
            snapshot=api_messages_request_snapshot(routed.request),
            request_id=request_id,
        )

        if self._settings.log_raw_api_payloads:
            # Lazy: full history dump is only materialized when opted in.
            logger.debug(f"{raw_log_label} [{{}}]: {{}}", request_id, raw_log_payload())

        input_tokens = self._token_counter(
            routed.request.messages,
            routed.request.system,
            routed.request.tools,
        )
        return traced_async_stream(
            provider.stream_response(
                routed.request,
                input_tokens=input_tokens,
                request_id=request_id,
                thinking_enabled=routed.resolved.thinking_enabled,
            ),
            stage="egress",
            source="api",
            complete_event=(
                "api.responses.stream_completed"
                if wire_api == "responses"
                else "api.response.stream_completed"
            ),
            interrupted_event=(
                "api.responses.stream_interrupted"
                if wire_api == "responses"
                else "api.response.stream_interrupted"
            ),
            chunk_event=None,
            extra={
                "request_id": request_id,
                "provider_id": routed.resolved.provider_id,
                "gateway_model": routed.request.model,
            },
        )
