# Graph Report - claude-unbound  (2026-07-13)

## Corpus Check
- 440 files · ~319,235 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 8146 nodes · 18779 edges · 314 communities (230 shown, 84 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 968 edges (avg confidence: 0.63)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ff788dd2`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Settings
- MessagesRequest
- test_web_server_tools.py
- TreeQueueManager
- ProviderRegistry
- anthropic.py
- IncomingMessage
- SmokeConfig
- registry.py
- SessionStore
- SSEBuilder
- _make_incoming
- get_token_count
- admin_routes.py
- TestProviderRateLimiter
- CLISession
- claude_cli_matrix.py
- _make_provider
- test_anthropic_messages.py
- NimSettings
- MessagingPlatform
- admin.js
- runtime.py
- test_freebuff.py
- entrypoints.py
- test_cloudflare_ai.py
- FreebuffManager
- ClaudeMessageHandler
- test_request_utils.py
- test_entrypoints.py
- Module
- SSEEvent
- parse_cli_event
- ProviderConfig
- escape_md_v2
- request.py
- Product E2E Smoke Tests
- is_prefix_detection_request
- config.py
- RenderCtx
- test_discord_markdown.py
- transcribe_audio
- admin_config.py
- StreamRecoverySession
- test_handler.py
- test_converter.py
- format_sse_event
- ModelListResponseError
- test_launcher.py
- TreeRepository
- create_app
- test_dependencies.py
- GraphifyManager
- NvidiaNimProvider
- DiscordPlatform
- InvalidRequestError
- sse.py
- binary_manager.py
- OllamaProvider
- test_manager.py
- mcp_config.py
- GraphifyProjectRegistry
- test_modules.py
- trace_event
- TestSettings
- routes.py
- codex.py
- __init__.py
- stream_recovery.py
- transport.py
- loader.py
- stream.py
- test_gemini.py
- TestPerModelMapping
- base.py
- test_freebuff_credentials.py
- test_llamacpp.py
- Path
- test_open_router.py
- Freebuff2API Admin Panel - Functionality Overhaul Summary
- ResponsesStreamAssembler
- LMStudioProvider
- AnthropicMessagesTransport
- test_adapters.py
- defaults.py
- anthropic.go
- stringValue
- request.py
- tokenPool
- .get_instance
- install.sh
- test_admin.py
- optimization_handlers.py
- TelegramPlatform
- test_smoke_config.py
- test_long_context_fallback.py
- test_mcp_config_async.py
- e2e.py
- CLISessionManager
- TestExtractTextFromContent
- request.py
- test_groq.py
- map_error
- test_codestral.py
- configure_logging
- mcp_router.py
- stable_session_key
- .refreshSession
- test_cerebras.py
- test_mistral.py
- tools.py
- ModelRegistry
- extract_provider_stream_usage
- test_installers.py
- File-by-File Implementation Plan
- test_context_length_clamp.py
- test_claude_mcp.py
- test_parsers.py
- test_conversion.py
- Server
- test_import_boundaries.py
- PendingVoiceRegistry
- OpenAIChatTransport
- build_codex_model_catalog
- ._handle_voice_note
- conftest.py
- AuthenticationError
- EmittedNativeSseTracker
- ThinkTagParser
- freebuff_status.py
- _make_tool_assembler
- ._format_event
- Freebuff2API
- test_feature_manifest.py
- Freebuff2API UX Fixes - Loading Delay & Color Issues
- parse_sse_text
- GraphifyProject
- Choose A Provider
- TranscriptBuffer
- _SnapshotQueue
- _test_e2e.py
- Architecture
- Message
- append_system_directive
- 🤖 Claude Unbound
- ci.sh
- .reset
- TestTreeQueueManager
- input.py
- uninstall.sh
- first_local_provider_model_id
- stream.py
- ._on_telegram_voice
- render_markdown_to_discord
- CloudflareAiProvider
- request.py
- test_kimi.py
- FakePlatform
- session.py
- stream_state.py
- .fire_and_forget
- OpenAIChatRecovery
- Config
- normalize_gfm_tables
- OpenAIToolCallAssembler
- test_config_extensibility_product_live.py
- Examples
- require_api_key
- MessagingRateLimiter
- test_admin_graphify.py
- test_routes_optimizations.py
- test_uninstallers.py
- __init__.py
- GlobalRateLimiter
- TestTreeQueueManager
- AGENTIC DIRECTIVE
- provider_catalog.py
- app.py
- AGENTIC DIRECTIVE
- Contributing to `Gelvey/claude-unbound`
- .__init__
- dump_raw_messages_request
- .get_actual_status
- request.py
- test_process_registry.py
- _provider
- UpstreamClient
- Extension Checklists
- RuntimeError
- Custom Modules for Claude Unbound
- test_ci_scripts.py
- .feed
- test_model_listing.py
- AnthropicSseEvent
- _cf_models_payload
- .convert_system_prompt
- module_settings.py
- ensureFreebuffSystemMarker
- _parse_allowed_channels
- test_voice_handlers.py
- test_mcp_proxy.py
- Connect Your Client
- Development
- ContentChunk
- TestTransportHeaderMerge
- ContentType
- build_rendering_profile
- ._create_transcript_and_render_ctx
- register_messaging_platform
- ._build_request_body
- .set_current_task
- test_orphan_close_tag_stripped
- test_orphan_close_tag_at_end
- writeClaudeStreamingResponse
- start_mcp.sh
- writeClaudeStreamingResponse
- .on_shutdown
- .edit_message
- api target
- test_openrouter_free_model_ids_handles_common_shapes
- launcher.sh
- mcp_proxy_tool.py
- _verify_launcher.py
- _JsonResponse
- test_freebuff_binary_manager.py
- auth target
- cli target
- tools.py
- clients target
- config target
- .cli_command
- .intercept
- .optimizer
- .reroute
- .router
- .token_counter
- .trace_listener
- discord target
- config_generator.py
- stop_mcp.sh
- __init__.py
- __init__.py
- extensibility target
- __init__.py
- verify_freebuff_fix.sh
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- FCC_ALLOW_NO_PROVIDER_SMOKE
- FCC_ENV_FILE
- FCC_LIVE_SMOKE
- FCC_SMOKE_CLAUDE_BIN
- FCC_SMOKE_DISCORD_CHANNEL_ID
- FCC_SMOKE_INTERACTIVE
- .__init__
- _cf_models_payload
- FCC_SMOKE_MODEL_* overrides
- .convert_tools
- FCC_SMOKE_NIM_EXTRA_MODELS
- free-claude-code
- github.com/Quorinex/Freebuff2API
- mcp-router
- FCC_SMOKE_NIM_MODELS
- FCC_SMOKE_OPENROUTER_FREE_MODELS
- FCC_SMOKE_PROVIDER_MATRIX
- FCC_SMOKE_RUN_VOICE
- FCC_SMOKE_TARGETS
- FCC_SMOKE_TELEGRAM_CHAT_ID
- FCC_SMOKE_TIMEOUT_S
- smoke/features.py
- harness_bug failure class
- llamacpp target
- lmstudio target
- messaging target
- missing_env failure class
- nvidia_nim_cli target
- ollama target
- openrouter_free_cli target
- smoke/prereq directory
- probe_timeout failure class
- smoke/product directory
- product_failure failure class
- providers target
- rate_limit target
- target_disabled failure class
- telegram target
- tools target
- upstream_unavailable failure class
- voice target
- ContentType
- .collect_text
- build_request_body
- retryable_upstream_status
- writeClaudeStreamingResponse
- .mcp_server
- _claude_tab.sh
- test_composio_test_uses_httpx_timeout
- .provider
- .set_current_task
- .cleanup
- .list_model_ids
- test_orphan_close_tag_stripped
- test_orphan_close_tag_at_end
- test_orphan_close_tag_parametrized
- test_think_tag_parser_flush_buffered_text
- test_think_tag_parser_unicode
- optimization_handlers.py
- .get_tree_count

## God Nodes (most connected - your core abstractions)
1. `Settings` - 376 edges
2. `MessagesRequest` - 230 edges
3. `ProviderConfig` - 187 edges
4. `SmokeConfig` - 137 edges
5. `Message` - 126 edges
6. `create_app()` - 122 edges
7. `SSEBuilder` - 111 edges
8. `IncomingMessage` - 104 edges
9. `NimSettings` - 101 edges
10. `ProviderRegistry` - 93 edges

## Surprising Connections (you probably didn't know these)
- `test_warn_if_process_auth_token_logs_warning()` --indirect_call--> `Settings`  [INFERRED]
  tests/api/test_app_lifespan_and_errors.py → config/settings.py
- `test_warn_if_process_auth_token_skips_explicit_dotenv_config()` --indirect_call--> `Settings`  [INFERRED]
  tests/api/test_app_lifespan_and_errors.py → config/settings.py
- `mock_platform()` --indirect_call--> `MessagingPlatform`  [INFERRED]
  tests/conftest.py → messaging/platforms/base.py
- `ConfigSectionSpec` --uses--> `Settings`  [INFERRED]
  api/admin_config.py → config/settings.py
- `ConfigFieldSpec` --uses--> `Settings`  [INFERRED]
  api/admin_config.py → config/settings.py

## Import Cycles
- 1-file cycle: `messaging/platforms/telegram.py -> messaging/platforms/telegram.py`
- 3-file cycle: `api/__init__.py -> api/app.py -> api/routes.py -> api/__init__.py`
- 3-file cycle: `messaging/command_dispatcher.py -> messaging/commands.py -> messaging/handler.py -> messaging/command_dispatcher.py`

## Hyperedges (group relationships)
- **Default smoke targets** — smoke_readme_targets, smoke_readme_api_target, smoke_readme_auth_target, smoke_readme_cli_target, smoke_readme_clients_target, smoke_readme_config_target, smoke_readme_extensibility_target, smoke_readme_messaging_target, smoke_readme_providers_target, smoke_readme_tools_target, smoke_readme_rate_limit_target, smoke_readme_lmstudio_target, smoke_readme_llamacpp_target, smoke_readme_ollama_target [EXTRACTED 1.00]
- **Heavy opt-in smoke targets** — smoke_readme_targets, smoke_readme_nvidia_nim_cli_target, smoke_readme_openrouter_free_cli_target, smoke_readme_telegram_target, smoke_readme_discord_target, smoke_readme_voice_target [EXTRACTED 1.00]
- **Smoke failure classes** — smoke_readme_failure_classes, smoke_readme_missing_env, smoke_readme_upstream_unavailable, smoke_readme_probe_timeout, smoke_readme_product_failure, smoke_readme_harness_bug, smoke_readme_target_disabled [EXTRACTED 1.00]

## Communities (314 total, 84 thin omitted)

### Community 0 - "Settings"
Cohesion: 0.02
Nodes (75): Skip suggestion mode requests., Mock filepath extraction requests., Run optimization handlers in order. Returns first match or None., Fast prefix detection - return command prefix without API call., Mock quota probe requests., Skip title generation requests., try_filepath_mock(), try_optimizations() (+67 more)

### Community 1 - "MessagesRequest"
Cohesion: 0.03
Nodes (119): is_prefix_detection_request(), is_quota_check_request(), Check if this is a quota probe request.      Quota checks are typically simple r, Check if this is a fast prefix detection request.      Prefix detection requests, Message, MessagesRequest, test_messages_request_accepts_adaptive_thinking_type(), test_messages_request_accepts_anthropic_server_tool_without_input_schema() (+111 more)

### Community 2 - "test_web_server_tools.py"
Cohesion: 0.03
Nodes (124): AbstractResolver, ResolvedModel, RoutedMessagesRequest, Tool, anthropic_sse_streaming_response(), ApiRequestPipeline, _graphify_project_directive(), _http_status_for_unexpected_pipeline_exception() (+116 more)

### Community 3 - "TreeQueueManager"
Cohesion: 0.02
Nodes (120): Platform-agnostic messaging layer., MessageNode, MessageState, MessageTree, Any, Enum, Tree data structures for message queue.  Contains MessageState, MessageNode, and, Create from dictionary (JSON deserialization). (+112 more)

### Community 4 - "ProviderRegistry"
Cohesion: 0.05
Nodes (59): Register a messaging platform factory., Event, Raised when the server is not ready (e.g. app lifespan did not wire state)., ServiceUnavailableError, ProviderRegistry, Cache and clean up provider instances by provider id., Return whether a provider for this id is already in the cache., Remove a cached provider and its model cache so the next ``get`` creates a fresh (+51 more)

### Community 5 - "anthropic.py"
Cohesion: 0.08
Nodes (50): API layer for Claude Code Proxy., _AnthropicBlockBase, ContentBlockDocument, ContentBlockImage, ContentBlockRedactedThinking, ContentBlockServerToolUse, ContentBlockText, ContentBlockThinking (+42 more)

### Community 6 - "IncomingMessage"
Cohesion: 0.06
Nodes (19): Tests for tree-based message queue system., Test MessageState enum., Test state enum values., Test MessageNode dataclass., Test creating a message node., Test TreeQueueManager class., Test creating a new tree., Test adding a reply to existing tree. (+11 more)

### Community 7 - "SmokeConfig"
Cohesion: 0.11
Nodes (45): ProviderModel, Return one smoke model per configured provider, independent of MODEL_*., Return the NVIDIA NIM models for Claude Code CLI characterization., Return OpenRouter free models for Claude Code CLI characterization., SmokeConfig, ConversationDriver, echo_tool_schema(), Drive multi-turn Anthropic-compatible conversations through the server. (+37 more)

### Community 8 - "registry.py"
Cohesion: 0.04
Nodes (69): ConfiguredChatModelRef, A unique configured chat model reference and the env keys that set it., BaseProvider, ABC, Any, Eagerly validate/build the upstream request before opening an SSE stream., Release any resources held by this provider., Return the model ids currently advertised by this provider. (+61 more)

### Community 9 - "SessionStore"
Cohesion: 0.04
Nodes (78): datetime, get_status_for_event(), Any, CLI event types and status-line mapping for transcript / UI updates., Return status string for event type, or None if no status update needed., dispatch_command(), message_kind_for_command(), parse_command_base() (+70 more)

### Community 10 - "SSEBuilder"
Cohesion: 0.07
Nodes (22): Canonical Anthropic-style SSE sequence for provider-side streaming errors., ContentBlockManager, _encoder_or_none(), map_stop_reason(), _normalize_task_run_in_background(), SSE event builder for Anthropic-format streaming responses., Record OpenAI tool call id before ``content_block_start`` (split-stream provider, Record tool name fragments as they arrive from chunked OpenAI streams. (+14 more)

### Community 11 - "_make_incoming"
Cohesion: 0.03
Nodes (41): _make_incoming(), _make_tree(), Updating state of a nonexistent node should not raise., Adding a node with nonexistent parent should raise ValueError., Create a minimal IncomingMessage for testing., Queue snapshot should return items in FIFO order., Enqueue should return 1-indexed position., get_children returns child nodes. (+33 more)

### Community 12 - "get_token_count"
Cohesion: 0.04
Nodes (47): clear_token_count_memo(), _count_message_tokens(), _count_system_tokens(), _count_text_tokens(), get_token_count(), _memoized_count(), Any, Token estimation for Anthropic-compatible requests.  Counting re-encodes convers (+39 more)

### Community 13 - "admin_routes.py"
Cohesion: 0.05
Nodes (83): admin_asset(), admin_module_tabs(), admin_page(), admin_status(), apply_mcp_config(), apply_sftp_config(), _asset_response(), _check_local_provider() (+75 more)

### Community 14 - "TestProviderRateLimiter"
Cohesion: 0.07
Nodes (44): Reset singleton (for testing)., RuntimeError, make_openai_compat_stream_request(), Shared MagicMock request objects for OpenAI-compatible provider tests., Minimal request stub matching :meth:`OpenAIChatTransport._build_request_body` ne, Native Anthropic transport: HTTP 429 and upstream 5xx are retried inside execute, Repeated upstream 5xx exhausts execute_with_retry; user message matches mapping., HTTP 400 from upstream is not retried; single send (passthrough limiter). (+36 more)

### Community 15 - "CLISession"
Cohesion: 0.04
Nodes (43): Shared contracts for client CLI subprocess adapters., Claude Code client CLI adapter., Client CLI adapter implementations., get_client_cli_adapter(), Internal client CLI adapter registry., Return a registered client CLI adapter by id., CLI integration for Claude Code., CLI Session Manager for Multi-Instance Claude CLI Support  Manages a pool of CLI (+35 more)

### Community 16 - "claude_cli_matrix.py"
Cohesion: 0.09
Nodes (65): _agent_result_count(), _agent_tool_count(), _basic_text(), _build_claude_cli_command(), classify_probe(), ClaudeCliRun, CliMatrixOutcome, _coerce_timeout_text() (+57 more)

### Community 17 - "_make_provider"
Cohesion: 0.07
Nodes (47): _assert_error_not_in_text_deltas_after_tool(), _assert_no_content_deltas_after_error_text(), AsyncStreamMock, _collect_stream(), _make_chunk(), _make_provider(), _make_provider_with_thinking_enabled(), _make_request() (+39 more)

### Community 18 - "test_anthropic_messages.py"
Cohesion: 0.10
Nodes (20): assert_product_stream(), ClientProtocolDriver, ProviderMatrixDriver, CompletedProcess, Path, Resolve provider models and enforce matrix semantics for product smoke., Build recorded/representative client protocol requests., Start a local proxy server for a product scenario. (+12 more)

### Community 19 - "NimSettings"
Cohesion: 0.07
Nodes (17): NimSettings, BaseModel, Fixed NVIDIA NIM settings (not configurable via env)., build_request_body(), Build OpenAI-format request body from Anthropic request., Tests for config/settings.py and config/nim.py, Test that valid values within bounds are accepted., top_k >= -1 should be accepted. (+9 more)

### Community 20 - "MessagingPlatform"
Cohesion: 0.04
Nodes (53): AppRuntime, best_effort(), log_startup_failure(), Any, Exception, Application runtime composition and lifecycle ownership., Own optional messaging, CLI, session, and provider runtime resources., Warm validation status without blocking first-run/admin access. (+45 more)

### Community 21 - "admin.js"
Cohesion: 0.08
Nodes (70): addEnvRow(), allCurrentValues(), api(), apply(), byId(), changedValues(), clearSftpMessages(), createFormInput() (+62 more)

### Community 22 - "runtime.py"
Cohesion: 0.07
Nodes (30): is_filepath_extraction_request(), is_suggestion_mode_request(), is_title_generation_request(), Request detection utilities for API optimizations.  Detects quota checks, title, Check if this is a conversation title generation request.      Title generation, Check if this is a suggestion mode request.      Suggestion mode requests contai, Check if this is a filepath extraction request.      Filepath extraction request, Optimization handlers for fast-path API responses.  Each handler returns a Messa (+22 more)

### Community 23 - "test_freebuff.py"
Cohesion: 0.05
Nodes (51): FreebuffProvider, normalize_freebuff_base_url(), Any, Freebuff2API provider (OpenAI-compatible chat completions via managed proxy).  F, Return model ids, auto-detecting the container port if needed., Rebuild the OpenAI client after :attr:`_base_url` changed., Open the chat stream, refreshing the client if the proxy moved.          The aut, Return a base URL ending in ``/v1`` for the OpenAI SDK. (+43 more)

### Community 24 - "entrypoints.py"
Cohesion: 0.03
Nodes (33): Custom CLAUDE_WORKSPACE values do not override the fixed workspace., Custom CLAUDE_CLI_BIN values do not override the fixed binary., Constructor extras cannot override fixed Claude runtime settings., Test Settings configuration., Test that empty string converts to None for optional int fields., Test model setting exists and is a string., Test NVIDIA_NIM_DEFAULT_BASE is a constant., LM_STUDIO_BASE_URL env var is loaded into settings. (+25 more)

### Community 25 - "test_cloudflare_ai.py"
Cohesion: 0.04
Nodes (47): CloudflareAiProvider, Cloudflare Workers AI (OpenAI-compatible chat completions)., Derive the native Cloudflare /ai/models/search URL from the OpenAI-compat base U, Return text-generation model ids from the Cloudflare Workers AI API.          Ra, _create_cloudflare_ai(), Build a Cloudflare Workers AI provider and resolve its per-account base URL., _cf_models_payload(), _cf_models_response() (+39 more)

### Community 26 - "FreebuffManager"
Cohesion: 0.05
Nodes (43): FreebuffManager, Path, Return the deployment method ("docker" or "source")., Return the loaded auth tokens., Start the Freebuff2API process/container.          Returns:             True if, Start Freebuff2API as a Docker container., Start Freebuff2API as a native binary.          Uses asyncio subprocess with std, Wait for the Freebuff2API instance to respond to health checks. (+35 more)

### Community 27 - "ClaudeMessageHandler"
Cohesion: 0.05
Nodes (20): Test per-model fields and resolve_model()., Per-model fields default to None., MODEL_OPUS env var is loaded., Empty per-model override env vars are treated as unset., Test environment variables override model defaults., MODEL_SONNET env var is loaded., MODEL_HAIKU env var is loaded., MODEL_OPUS with invalid provider prefix raises ValidationError. (+12 more)

### Community 28 - "test_request_utils.py"
Cohesion: 0.07
Nodes (26): extract_command_prefix(), extract_filepaths_from_command(), _is_env_assignment(), Command parsing utilities for API optimizations., Return True when a token is a shell-style env assignment., Return command parts after leading shell-style env assignments., Extract the command prefix for fast prefix detection.      Parses a shell comman, Extract file paths from a command locally without API call.      Determines if t (+18 more)

### Community 29 - "test_entrypoints.py"
Cohesion: 0.07
Nodes (55): CaptureFixture, _admin_browser_open_enabled(), _claude_child_env(), launch_claude(), launch_codex(), Whether to open /admin when the server becomes reachable (FCC_OPEN_BROWSER)., Return a Claude Code environment that targets this proxy., Launch Claude Code with Claude Unbound proxy environment variables. (+47 more)

### Community 30 - "Module"
Cohesion: 0.07
Nodes (26): Module, Register a Starlette/FastAPI middleware class (added outside the trace middlewar, Register a constant system-prompt directive appended to every MessagesRequest., Register a custom tab in the admin UI., Contract exposed by a custom module.      A module sets ``FCC_MODULE = Module(.., _extract_module(), _log_error(), ModuleManager (+18 more)

### Community 31 - "SSEEvent"
Cohesion: 0.10
Nodes (19): Shared defaults used by config models and provider adapters., attach_provider_error_body(), Attach a streamed HTTP error body to an exception for later formatting., Any, build_request_body(), Any, Native Anthropic Messages request builder for Kimi (Moonshot)., Build JSON for Kimi Anthropic-compat ``POST …/messages``. (+11 more)

### Community 32 - "parse_cli_event"
Cohesion: 0.06
Nodes (40): parse_cli_event(), Any, CLI event parser for Claude Code CLI output.  This parser emits an ordered strea, Parse a CLI event and return a structured result.      Args:         event: Raw, CLI parser must not log raw error text unless LOG_RAW_CLI_DIAGNOSTICS is on., test_parse_cli_event_error_logs_metadata_by_default(), test_parse_cli_event_error_logs_text_when_log_raw_cli_enabled(), Tests for cli/ module. (+32 more)

### Community 33 - "ProviderConfig"
Cohesion: 0.06
Nodes (26): Get or create the singleton instance.          Args:             rate_limit: Req, remaining_wait() should return 0 when not blocked., remaining_wait() should decrease over time., is_blocked() should be False for a fresh limiter., Very high rate limit should not cause throttling., get_instance should return the same object., reset_instance should allow creating a new instance., wait_if_blocked should return False when not reactively blocked. (+18 more)

### Community 34 - "escape_md_v2"
Cohesion: 0.08
Nodes (42): escape_md_v2(), escape_md_v2_code(), escape_md_v2_link_url(), format_status(), mdv2_bold(), mdv2_code_inline(), Telegram MarkdownV2 utilities.  Renders common Markdown into Telegram MarkdownV2, Escape text for Telegram MarkdownV2. (+34 more)

### Community 35 - "request.py"
Cohesion: 0.08
Nodes (35): Exception, NVIDIA NIM provider implementation., Retry once with a downgraded body when NIM rejects a known field., NVIDIA NIM provider package., _alias_nim_schema_property_names(), _alias_nim_tool_parameters(), body_without_nim_tool_argument_aliases(), clone_body_without_chat_template() (+27 more)

### Community 36 - "Product E2E Smoke Tests"
Cohesion: 0.22
Nodes (9): Child process execution, Environment, Examples, Failure Classes, Product E2E Smoke Tests, Product Smoke Run, Required Local Commands, Targets (+1 more)

### Community 37 - "is_prefix_detection_request"
Cohesion: 0.12
Nodes (27): AdminConfigPayload, ComposioSetupPayload, ComposioTestPayload, GraphifyProjectPayload, McpConfigPayload, PermissionsPayload, BaseModel, Optional API key override for testing Composio connectivity. (+19 more)

### Community 38 - "config.py"
Cohesion: 0.11
Nodes (38): has_tool_use(), smoke_server(), _excerpt(), auth_headers(), Redact known secrets from a string before writing smoke artifacts., redacted(), collect_message_stream(), message_payload() (+30 more)

### Community 39 - "RenderCtx"
Cohesion: 0.08
Nodes (15): Create transcript buffer and render context for node processing., ErrorSegment, ABC, Any, Ordered transcript builder for messaging UIs (Telegram, etc.).  This module main, Apply a parsed event to the transcript., Render transcript with truncation (drop oldest segments)., RenderCtx (+7 more)

### Community 40 - "test_discord_markdown.py"
Cohesion: 0.08
Nodes (23): discord_bold(), discord_code_inline(), escape_discord(), escape_discord_code(), format_status(), Discord markdown utilities.  Discord uses standard markdown: **bold**, *italic*,, Escape text for Discord markdown (bold, italic, etc.)., Escape text for Discord code spans/blocks. (+15 more)

### Community 41 - "transcribe_audio"
Cohesion: 0.06
Nodes (42): _get_pipeline(), _load_audio(), Any, Path, Voice note transcription for messaging platforms.  Supports: - Local Whisper (cp, Load audio file to waveform dict. No ffmpeg required., Transcribe using transformers Whisper pipeline., Resolve short name to full Hugging Face model ID. (+34 more)

### Community 42 - "admin_config.py"
Cohesion: 0.08
Nodes (50): changed_pending_fields(), ConfigFieldSpec, ConfigSectionSpec, configured_env_files(), _display_value(), _dotenv_values_from_file(), _dotenv_values_from_text(), _effective_values_for_validation() (+42 more)

### Community 43 - "StreamRecoverySession"
Cohesion: 0.06
Nodes (33): is_retryable_stream_error(), BaseException, Return whether a provider stream error can be retried/recovered., Briefly hold downstream SSE so early stream cutoffs can be retried invisibly., Buffer ``event`` until holdback expires or cap is reached., Commit and return all held events., Drop held events without committing them downstream., RecoveryHoldbackBuffer (+25 more)

### Community 44 - "test_handler.py"
Cohesion: 0.06
Nodes (43): incoming_message_factory(), handler(), test_grandchild_reply_forks_from_branch_session(), test_sibling_replies_fork_from_parent_session_id(), handler(), handler_integration(), mock_async_gen(), test_concurrent_replies_to_different_trees() (+35 more)

### Community 45 - "test_converter.py"
Cohesion: 0.12
Nodes (43): MockBlock, MockMessage, Top-level reasoning replay avoids duplicating thinking into content., Parametrized user message conversion., Unknown block types should be silently skipped., Tool use with None input should not crash., Interleaved thinking, text, tool_use should preserve thinking+text order in cont, User message with text then tool_result should preserve order: user text first, (+35 more)

### Community 46 - "format_sse_event"
Cohesion: 0.12
Nodes (31): Track content-block state for native Anthropic SSE strings we emit to clients., accept_tool_json_repair(), continuation_suffix(), _copied_messages(), make_native_text_recovery_body(), make_native_tool_repair_body(), make_openai_text_recovery_body(), make_openai_tool_repair_body() (+23 more)

### Community 47 - "ModelListResponseError"
Cohesion: 0.05
Nodes (49): Base provider interface - extend this to implement your own provider., Return advertised model ids with optional provider capability metadata., Cerebras Inference (OpenAI-compatible) adapter., Cloudflare Workers AI provider (OpenAI-compatible chat completions).  The OpenAI, Cloudflare Workers AI (OpenAI-compat) adapter., Re-exports default upstream base URLs from the config provider catalog., ModelListResponseError, Raised when a provider model-list response cannot be parsed safely. (+41 more)

### Community 48 - "test_launcher.py"
Cohesion: 0.06
Nodes (46): _braced_body(), CompletedProcess, Path, Script checks for npx, socat, jq, uv when MCP script exists., Script creates ~/.fcc/mcp_config.json from example on first run., Script launches kitty with --listen-on unix socket., Script mentions all 3 tabs: MCP Router, Server, Claude Unbound CLI., Claude Unbound CLI tab waits for fcc-server before launching fcc-claude. (+38 more)

### Community 49 - "TreeRepository"
Cohesion: 0.08
Nodes (15): Tests for messaging/ module., Test messaging models., Test TreeQueueManager., Test TreeQueueManager initialization., Test IncomingMessage dataclass., Test tree is not busy when no messages., Test queue size is 0 for non-existent node., Test creating a tree and enqueueing. (+7 more)

### Community 50 - "create_app"
Cohesion: 0.16
Nodes (44): create_app(), Create and configure the FastAPI application., _local_client(), Path, Tests for MCP Router admin API routes., Updating the API key must not wipe user-added custom headers., Header lookup is case-insensitive: HTTP headers are not case-sensitive., If a downstream exception echoes the API key back, it must be redacted. (+36 more)

### Community 51 - "test_dependencies.py"
Cohesion: 0.04
Nodes (103): cleanup_provider(), _extract_graphify_repo_suffix(), get_provider(), get_provider_for_type(), get_settings(), Request, Dependency injection for FastAPI., Decode and strip a `:graphify-repo:<base64>` suffix from a token. (+95 more)

### Community 52 - "GraphifyManager"
Cohesion: 0.05
Nodes (39): _directory_size(), _ensure_graphify_venv(), _extract_jsonrpc_error(), _find_free_port(), _format_bytes(), GraphifyManager, _is_graphify_importable(), _is_module_importable() (+31 more)

### Community 53 - "NvidiaNimProvider"
Cohesion: 0.08
Nodes (45): InternalServerError, NvidiaNimProvider, NVIDIA NIM provider using official OpenAI client., _input_json_deltas(), _make_bad_request_error(), mock_rate_limiter(), MockBlock, MockMessage (+37 more)

### Community 54 - "DiscordPlatform"
Cohesion: 0.03
Nodes (45): Intents, _DiscordClient, DiscordPlatform, _get_discord(), _parse_allowed_channels(), Any, Discord Platform Adapter  Implements MessagingPlatform for Discord using discord, Adapter entry point used by the internal discord client. (+37 more)

### Community 55 - "InvalidRequestError"
Cohesion: 0.06
Nodes (59): _apply_openrouter_reasoning_policy(), build_base_native_anthropic_request_body(), build_openrouter_native_request_body(), _dump_request_fields(), _normalize_system_prompt_for_openrouter(), OpenRouterExtraBodyError, OpenRouterPolicySettings, Any (+51 more)

### Community 56 - "sse.py"
Cohesion: 0.04
Nodes (29): Any, Record provider-specific OpenAI tool-call metadata before block start., Builder for Anthropic SSE streaming events., Emit the final usage event.          ``input_tokens`` overrides the local estima, Emit a top-level ``event: error`` (not assistant text) for transport failures., Coerce streamed usage counters to int; non-integers become 0., State for a single streaming tool call., _safe_usage_int() (+21 more)

### Community 57 - "binary_manager.py"
Cohesion: 0.08
Nodes (45): _apply_patch(), binary_path(), binary_status(), build_from_source(), build_patched_docker_image(), check_container_running(), check_docker_available(), check_go_available() (+37 more)

### Community 58 - "OllamaProvider"
Cohesion: 0.07
Nodes (33): OllamaProvider, Response, Ollama provider using native Anthropic Messages API., Create a streaming native Anthropic messages response., Query Ollama's native local model-list endpoint., _create_ollama(), mock_rate_limiter(), MockMessage (+25 more)

### Community 59 - "test_manager.py"
Cohesion: 0.16
Nodes (46): _async_process_mock(), _build_manager(), _mcp_ok_response(), Any, MonkeyPatch, Path, Tests for GraphifyManager lifecycle and project indexing., Default GRAPHIFY_STATELESS=true appends --stateless to graphify.serve argv. (+38 more)

### Community 60 - "mcp_config.py"
Cohesion: 0.07
Nodes (30): load_mcp_config(), _mask_env(), _mask_headers(), McpBackend, McpConfig, McpConfigResult, BaseModel, Path (+22 more)

### Community 61 - "GraphifyProjectRegistry"
Cohesion: 0.11
Nodes (41): graphify_add_project(), graphify_remove_project(), Add or update a Graphify project., Remove a Graphify project by base64-encoded path., GraphifyProjectRegistry, Pydantic models for the Graphify project registry., Root registry of Graphify projects., Graphify MCP integration for Claude Unbound. (+33 more)

### Community 62 - "test_modules.py"
Cohesion: 0.15
Nodes (41): get_module_system_directives(), Return a copy of the module-supplied system directives., get_trace_listeners(), Return a copy of the registered trace listeners., module_manager_factory(), Path, Tests for the custom module loader and registration surfaces., Return a factory that loads modules from the temp dir into a fresh app. (+33 more)

### Community 63 - "trace_event"
Cohesion: 0.09
Nodes (40): add_trace_listeners(), api_messages_request_snapshot(), configure_trace_payloads(), provider_chat_body_snapshot(), provider_native_messages_body_snapshot(), Any, Structured TRACE events for end-to-end request / CLI / provider logging.  Emitte, Remove previously appended trace listeners (used by tests). (+32 more)

### Community 64 - "TestSettings"
Cohesion: 0.07
Nodes (23): iter_provider_stream_error_sse_events(), Any, Yield message_start (if needed), a text block with the error, then message_delta, AnthropicMessagesTransport, Any, Response, Parse the provider model-list response body., Parse provider model metadata; default to unknown capabilities. (+15 more)

### Community 65 - "routes.py"
Cohesion: 0.10
Nodes (26): configure_logging(), InterceptHandler, Path, Loguru-based structured logging configuration.  Structured logs are written as J, Map a loguru level name to the closest stdlib logging level., Configure loguru with JSON output to log_file and intercept stdlib logging., Remove obvious API tokens and secrets before JSON log line emission., Format record as JSON with context vars at top level.     Returns a format templ (+18 more)

### Community 66 - "codex.py"
Cohesion: 0.11
Nodes (29): _base_codex_env(), _codex_event_to_parser_events(), CodexCliAdapter, _custom_tool_input_text(), _ensure_v1_url(), _event_message(), _event_output_index(), _event_response_id() (+21 more)

### Community 67 - "__init__.py"
Cohesion: 0.10
Nodes (33): extract_text_from_content(), get_block_attr(), get_block_type(), Any, Content block helpers for Anthropic-compatible payloads., Return a content block type when present., Extract concatenated text from message content., Get an attribute from a Pydantic model, lightweight object, or dict. (+25 more)

### Community 68 - "stream_recovery.py"
Cohesion: 0.09
Nodes (30): Return Anthropic tool input schemas keyed by tool name., Raised internally when an upstream stream ends without a terminal marker., tool_schemas_by_name(), TruncatedProviderStreamError, CreateStream, OpenAIChatRecovery, Any, Exception (+22 more)

### Community 69 - "transport.py"
Cohesion: 0.21
Nodes (21): CliParseState, Mutable line-parser state for a single client CLI process run., Parse one Claude Code JSONL line into existing parser-ready events., Parse one Codex JSONL line into existing parser-ready events., test_claude_adapter_invalid_stdout_json_becomes_raw_event(), test_claude_adapter_synthesizes_session_info_once(), test_codex_adapter_completed_output_is_fallback_for_unseen_message_item(), test_codex_adapter_completed_output_is_fallback_for_unseen_tool_item() (+13 more)

### Community 70 - "loader.py"
Cohesion: 0.08
Nodes (39): ModuleCliCommand, ModuleMcpServer, ModuleSettingSpec, Dataclass contract and type aliases for custom modules., One Settings field a module declares., A CLI subcommand registered by a module., An MCP server backend a module wants in mcp_config.json., discover_module_paths() (+31 more)

### Community 71 - "stream.py"
Cohesion: 0.18
Nodes (15): cachedSession, formatElapsedDuration(), formatWaitDuration(), Context, Duration, tokenPool, UpstreamClient, Time (+7 more)

### Community 72 - "test_gemini.py"
Cohesion: 0.11
Nodes (23): gemini_config(), mock_rate_limiter(), MockMessage, MockRequest, Tests for Google AI Studio Gemini (OpenAI-compatible) provider., Regression for issue #542: SDK merge must not send top-level google., When thinking is off, Gemini uses reasoning_effort none (Gemini 2.5 convention)., Mock the global rate limiter to prevent waiting. (+15 more)

### Community 73 - "TestPerModelMapping"
Cohesion: 0.09
Nodes (10): Queue with snapshot/remove helpers, backed by a deque and a set index., Add a node to the processing queue.          Returns:             Queue position, Get the next node ID from the queue.          Returns None if queue is empty., Get a snapshot of the current queue order.          Returns:             List of, Get number of messages waiting in queue., Remove node_id from the internal queue if present.          Caller must hold the, Add node to queue. Caller must hold lock (e.g. via with_lock)., Return current queue contents in FIFO order (read-only copy). (+2 more)

### Community 74 - "base.py"
Cohesion: 0.08
Nodes (22): Limits, provider_http_limits(), provider_http_timeout(), Build the httpx timeout shared by provider transports., Build connection-pool limits with a long keep-alive expiry.      httpx defaults, Get or create a provider-scoped limiter instance.          A ``rate_limit`` of 0, Return whether this limiter matches the requested runtime config., _ChatProvider (+14 more)

### Community 75 - "test_freebuff_credentials.py"
Cohesion: 0.15
Nodes (26): credentials_path(), credentials_status(), Any, Path, Read Freebuff auth tokens from ~/.config/manicode/credentials.json.  The Freebuf, Return the resolved credentials file path., Read all auth tokens from the Freebuff credentials file.      Returns:         L, Return credential status for the admin panel.      Returns:         Dict with `` (+18 more)

### Community 76 - "test_llamacpp.py"
Cohesion: 0.08
Nodes (30): LlamaCppProvider, Llama.cpp provider implementation., Llama.cpp provider using native Anthropic Messages endpoint., _create_llamacpp(), llamacpp_provider(), llamacpp_config(), llamacpp_provider(), mock_rate_limiter() (+22 more)

### Community 77 - "Path"
Cohesion: 0.12
Nodes (19): MonkeyPatch, Path, TestClient, Test that /admin/api/config reflects settings.json state., Config API shows true when settings.json has bypassPermissions., Config API shows false when settings.json absent., Applying toggle writes bypassPermissions to settings.json., Applying toggle removes bypassPermissions from settings.json. (+11 more)

### Community 78 - "test_open_router.py"
Cohesion: 0.06
Nodes (42): OpenRouterProvider, Any, Emit the Anthropic SSE error shape expected by Claude clients., OpenRouter provider using the native Anthropic-compatible messages API., Internal helper for tests and direct request dispatch., Return OpenRouter's Anthropic-compatible messages headers., Return OpenRouter's OpenAI-compatible model-list headers., Only advertise OpenRouter models that can run Claude Code tools. (+34 more)

### Community 79 - "Freebuff2API Admin Panel - Functionality Overhaul Summary"
Cohesion: 0.04
Nodes (45): 1. **Status Detection Was Broken**, 2. **Docker Permission Issues**, 3. **UI Shows Inaccurate Status**, 4. **Silent Failures**, `api/admin_routes.py`, `api/admin_static/admin.js`, Backend (Python), Docker Permission Handling (+37 more)

### Community 80 - "ResponsesStreamAssembler"
Cohesion: 0.17
Nodes (9): _BlockState, _event_index(), _openai_error_from_anthropic_error(), Any, Assemble Responses SSE events from indexed Anthropic content blocks., ResponsesStreamAssembler, _string_value(), _TextBlockState (+1 more)

### Community 81 - "LMStudioProvider"
Cohesion: 0.07
Nodes (34): LMStudioProvider, LM Studio provider implementation., LM Studio provider using native Anthropic Messages endpoint., LM Studio provider - Anthropic-compatible local API., _create_lmstudio(), lmstudio_provider(), lmstudio_config(), lmstudio_provider() (+26 more)

### Community 82 - "AnthropicMessagesTransport"
Cohesion: 0.11
Nodes (33): _allocate_new_segment(), _delta_type_to_block_kind(), format_native_sse_event(), is_terminal_openrouter_done_event(), NativeSseBlockPolicyState, parse_native_sse_event(), Any, Shared native Anthropic SSE thinking policy, block remapping, and overlap repair (+25 more)

### Community 83 - "test_adapters.py"
Cohesion: 0.08
Nodes (37): CliInvocation, CliTaskRequest, A single prompt execution request for a managed client CLI process., Concrete subprocess invocation assembled by a client CLI adapter., Build the subprocess invocation for a managed task run., _claude_auth_token(), ClaudeCliAdapter, Any (+29 more)

### Community 84 - "defaults.py"
Cohesion: 0.46
Nodes (7): dump_raw_messages_request(), Public JSON-ready dict of Anthropic public request fields (for native adapters)., Contract: Anthropic ``cache_control`` breakpoints survive native serialization., _request_with_cache_breakpoints(), test_cache_control_survives_dump_on_message_blocks(), test_cache_control_survives_dump_on_system_blocks(), test_cache_control_survives_dump_on_tools()

### Community 85 - "anthropic.go"
Cohesion: 0.34
Nodes (14): Builder, appendClaudeFinalContentEvents(), appendClaudeMessageDeltaAndStop(), convertOpenAIStreamPayloadToClaudeEvents(), effectiveOpenAIFinishReason(), finalizeClaudeStream(), nextClaudeBlockIndex(), stopTextContentBlock() (+6 more)

### Community 86 - "stringValue"
Cohesion: 0.13
Nodes (41): boolValue(), budgetToReasoningEffort(), buildOpenAIToolResultMessage(), collectReasoningTexts(), collectReasoningTextValues(), convertClaudeImagePartToOpenAI(), convertClaudeMessageContent(), convertClaudeMessagesRequestToOpenAI() (+33 more)

### Community 87 - "request.py"
Cohesion: 0.08
Nodes (33): build_base_request_body(), _openai_reject_native_only_top_level_fields(), OpenAIConversionError, Exception, StrEnum, Raised when Anthropic content cannot be converted to OpenAI chat without data lo, How assistant reasoning history is replayed to OpenAI-compatible providers., OpenAI chat providers may only convert known top-level request fields.      Firs (+25 more)

### Community 88 - "tokenPool"
Cohesion: 0.15
Nodes (15): managedRun, Context, tokenPool, Logger, Time, UpstreamClient, WaitGroup, NewRunManager() (+7 more)

### Community 89 - ".get_instance"
Cohesion: 0.09
Nodes (19): Stop the background worker so process shutdown doesn't hang., Shutdown and clear the singleton instance (safe to call multiple times)., Get the singleton instance of the limiter.          ``rate_limit`` and ``rate_wi, Initialize and connect to Discord., Test that FloodWait exceptions pause the worker., Error message with 'retry after N' parses the wait seconds., Tests for MessagingRateLimiter., Non-flood exception doesn't trigger pause. (+11 more)

### Community 90 - "install.sh"
Cohesion: 0.13
Nodes (31): add_path_entry(), add_uv_to_path(), clone_or_update_repo(), create_wrappers(), fail(), install_claude_if_missing(), install_codex_if_missing(), install_or_update_uv() (+23 more)

### Community 91 - "test_admin.py"
Cohesion: 0.19
Nodes (32): _clear_process_config(), client(), _local_client(), Env file does not contain CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS., Provide a TestClient bound to the local admin address., _set_home(), test_admin_apply_omits_stale_fixed_claude_runtime_settings(), test_admin_apply_omits_stale_zai_base_url() (+24 more)

### Community 92 - "optimization_handlers.py"
Cohesion: 0.10
Nodes (12): KimiProvider, Response, Kimi (Moonshot) provider using native Anthropic-compatible Messages., Kimi provider using Anthropic-compatible Messages at api.moonshot.ai/anthropic/v, Models are listed from the OpenAI-compat root, not ``/anthropic/v1``., Kimi (Moonshot) provider exports., _create_kimi(), kimi_config() (+4 more)

### Community 93 - "TelegramPlatform"
Cohesion: 0.11
Nodes (26): Telegram messaging platform adapter.      Uses python-telegram-bot (BoT API) for, TelegramPlatform, telegram_platform(), edit_message with text > 4096 raises TelegramError (BadRequest)., edit_message with empty string - Telegram accepts (no-op edit)., send_message with empty string - Telegram may reject; we pass through., Update with message.photo but no text returns early without calling handler., message to edit not found' returns None without retry. (+18 more)

### Community 94 - "test_smoke_config.py"
Cohesion: 0.07
Nodes (52): Item, Metafunc, Session, _disabled_provider_param(), provider_model_id(), provider_model_params(), provider_xdist_group(), Any (+44 more)

### Community 95 - "test_long_context_fallback.py"
Cohesion: 0.18
Nodes (16): _drain(), FakeProvider, Any, MonkeyPatch, StreamingResponse, Long-context fallback rerouting via LONG_CONTEXT_MODEL / THRESHOLD., _request(), _run() (+8 more)

### Community 96 - "test_mcp_config_async.py"
Cohesion: 0.09
Nodes (32): get_router_status(), merge_module_backends(), _parse_jsonrpc_results(), Any, Merge module-registered MCP backends into a ``servers``-style dict.      Each mo, Send JSON-RPC messages to the router socket and return raw response.      Uses a, Extract parsed result payloads from JSON-RPC response lines., Query the router for live backend status.      Returns {running: false} if the s (+24 more)

### Community 98 - "CLISessionManager"
Cohesion: 0.09
Nodes (19): CLISessionManager, Register the real session ID from CLI output., Remove a session from the manager., Get session statistics., Manages multiple CLISession instances for parallel conversation processing., Initialize the session manager.          Args:             workspace_path: Worki, Get an existing session or create a new one.          Returns:             Tuple, CLISession (+11 more)

### Community 99 - "TestExtractTextFromContent"
Cohesion: 0.06
Nodes (26): Shared strict sliding-window rate limiting primitives., Strict sliding window limiter.      Guarantees: at most ``rate_limit`` acquisiti, StrictSlidingWindowLimiter, GlobalRateLimiter, Any, BaseException, Global rate limiter for API requests., Wait if currently rate limited or throttle to meet quota.          Returns: (+18 more)

### Community 100 - "request.py"
Cohesion: 0.10
Nodes (33): Any, build_request_body(), _downgrade_forced_tool_choice(), _has_replayable_thinking_before_tool_use(), _has_replayable_tool_thinking(), _has_tool_history(), _has_tool_history_blocks(), _is_server_listed_tool() (+25 more)

### Community 101 - "test_groq.py"
Cohesion: 0.10
Nodes (22): GroqProvider, Groq API using ``https://api.groq.com/openai/v1/chat/completions``., _create_groq(), groq_config(), groq_provider(), mock_rate_limiter(), MockMessage, MockRequest (+14 more)

### Community 102 - "map_error"
Cohesion: 0.06
Nodes (57): append_request_id(), Append request_id suffix when available., HTTPStatusError, _append_request_id_lines(), _body_from_response(), _cap_text_bytes(), _error_type_hint_from_body(), extract_provider_error_detail() (+49 more)

### Community 103 - "test_codestral.py"
Cohesion: 0.07
Nodes (29): CodestralProvider, Any, Mistral Codestral provider (OpenAI-compatible chat on codestral.mistral.ai)., Codestral host using ``https://codestral.mistral.ai/v1/chat/completions``., Mistral Codestral provider (codestral.mistral.ai) exports., Any, build_request_body(), Any (+21 more)

### Community 104 - "configure_logging"
Cohesion: 0.10
Nodes (23): Write ``bypassPermissions`` into ``~/.claude/settings.json``.      When *enabled, write_claude_permissions_setting(), apply_admin_config(), _build_composio_entry(), _filtered_values(), _invoke_admin_restart_callback(), _lookup_composio_api_key(), _mask_mcp_config() (+15 more)

### Community 105 - "mcp_router.py"
Cohesion: 0.11
Nodes (25): Content, JSONRPCMessage, _activate(), Backend, _build_server(), _deactivate(), _forward_call(), _handle_client() (+17 more)

### Community 106 - "stable_session_key"
Cohesion: 0.12
Nodes (18): _conversation_seed(), _metadata_user_id(), Any, Stable per-conversation keys for provider prompt-cache routing.  Providers with, Return a stable opaque cache-routing key for this conversation, or None., stable_session_key(), _stable_text(), Any (+10 more)

### Community 107 - ".refreshSession"
Cohesion: 0.19
Nodes (22): Maintains an ordered, truncatable transcript of events., TranscriptBuffer, _ctx(), Render with 200+ segments exercises O(n) truncation (deque popleft)., When a segment's render() raises, that segment is skipped and rest is rendered., When all segments dropped, status-only output; long status returned as-is., When all segments exceed limit, preserve tail of last segment (not just marker+s, test_transcript_order_thinking_tool_text() (+14 more)

### Community 108 - "test_cerebras.py"
Cohesion: 0.10
Nodes (23): CerebrasProvider, Cerebras API at ``https://api.cerebras.ai/v1/chat/completions``., _create_cerebras(), cerebras_config(), cerebras_provider(), mock_rate_limiter(), MockMessage, MockRequest (+15 more)

### Community 109 - "test_mistral.py"
Cohesion: 0.08
Nodes (24): MistralProvider, Mistral La Plateforme provider implementation (OpenAI-compatible chat completion, Mistral API using ``https://api.mistral.ai/v1/chat/completions``., Mistral La Plateforme provider exports., _create_mistral(), mistral_config(), mistral_provider(), mock_rate_limiter() (+16 more)

### Community 110 - "tools.py"
Cohesion: 0.20
Nodes (28): ValueError, Raised when a Responses request cannot be converted deterministically., ResponsesConversionError, new_call_id(), call_id_from_item(), _convert_custom_tool(), _convert_function_tool(), _convert_namespace_tool() (+20 more)

### Community 111 - "ModelRegistry"
Cohesion: 0.11
Nodes (19): containsString(), ModelRegistry, buildModelMapping(), fetchSource(), Client, Context, Logger, Time (+11 more)

### Community 112 - "extract_provider_stream_usage"
Cohesion: 0.12
Nodes (15): extract_provider_stream_usage(), _field(), _int_or_none(), ProviderStreamUsage, Any, Map OpenAI-compat streamed usage to Anthropic usage fields.  Providers report ac, Provider-reported token usage for one completed stream., Non-cached input tokens per Anthropic usage semantics. (+7 more)

### Community 113 - "test_installers.py"
Cohesion: 0.12
Nodes (28): _braced_body(), CompletedProcess, Path, Run install.sh with given arguments and return the result., install.sh --dry-run prints the expected installation steps., install.sh --help prints the usage text., install.sh -h also prints the usage text., install.sh fails on unknown options. (+20 more)

### Community 114 - "File-by-File Implementation Plan"
Cohesion: 0.06
Nodes (31): 10. MCP Router integration — `api/graphify/mcp_backend.py`, 11. Packaging and dependencies, 12. Documentation, 1. MCP router reload behavior, 1. New package `api/graphify/`, 2. Dependency mechanism, 2. Settings — `config/settings.py`, 3. Admin config manifest — `api/admin_config.py` (+23 more)

### Community 115 - "test_context_length_clamp.py"
Cohesion: 0.19
Nodes (17): clamped_max_tokens_from_context_length_error(), Return a reduced ``max_tokens`` parsed from a context-length error.      Returns, _bad_request(), BadRequestError, Context-length 400 parsing and max_tokens clamp retry., test_ai_error_requires_integer_current_max_tokens(), test_ai_error_returns_none_when_input_alone_fills_context(), test_cloudflare_provider_retry_hook_clamps() (+9 more)

### Community 116 - "test_claude_mcp.py"
Cohesion: 0.15
Nodes (28): _atomic_write(), build_graphify_server_entry(), claude_json_path(), graphify_claude_server_registered(), _load_claude_json(), Any, Path, Register the local Graphify MCP server as a sibling of the MCP Router.  Graphify (+20 more)

### Community 117 - "test_parsers.py"
Cohesion: 0.13
Nodes (25): HeuristicToolParser, Stateful parser for raw text tool calls.      Some OpenAI-compatible models emit, test_task_tool_arguments_force_foreground_execution(), Empty string input should return empty filtered text and no tools., Flush when no tool is being parsed should return empty list., Unicode characters in function parameters., Malformed function tags should still be handled without crashing., test_garbage_interleaved() (+17 more)

### Community 118 - "test_conversion.py"
Cohesion: 0.08
Nodes (9): OpenAIResponsesAdapter, Any, Facade for OpenAI Responses protocol adaptation., Convert between OpenAI Responses and the proxy's Anthropic core path., openai_error_payload(), Any, Errors and error envelopes for OpenAI Responses compatibility., Return an OpenAI-compatible error envelope. (+1 more)

### Community 119 - "Server"
Cohesion: 0.09
Nodes (39): normalizeClaudeErrorType(), writeClaudeError(), writeClaudePassthroughError(), Server, cloneMap(), cloneSlice(), copyHeaders(), copyResponseBody() (+31 more)

### Community 120 - "test_import_boundaries.py"
Cohesion: 0.15
Nodes (26): ImportFrom, _importing_package_parts(), _imports_from(), _imports_matching(), _is_forbidden(), _module_fqn_from_path(), Path, Package import contract tests (static AST; dynamic ``importlib`` loads are not s (+18 more)

### Community 121 - "PendingVoiceRegistry"
Cohesion: 0.18
Nodes (18): cmd_fcc_init(), cmd_free_claude_code_serve(), cmd_python_c(), cmd_uvicorn_server_app(), python_exe(), Child-process commands for smoke (avoid nested ``uv run``).  Nested ``uv run`` c, Path, test_claude_cli_prompt_when_available() (+10 more)

### Community 122 - "OpenAIChatTransport"
Cohesion: 0.12
Nodes (14): OpenAIChatTransport, Any, Exception, Hook for provider-specific reasoning., Return a modified request body for one retry, or None., Return the body passed to the upstream OpenAI-compatible client., Add a stable ``prompt_cache_key`` when the provider or operator opts in., Hook for providers that must replay OpenAI tool-call metadata later. (+6 more)

### Community 123 - "build_codex_model_catalog"
Cohesion: 0.19
Nodes (25): build_codex_model_catalog(), _candidate_from_model_id(), _catalog_candidates(), _CatalogCandidate, _codex_catalog_entry(), _is_provider_model_ref(), Any, Path (+17 more)

### Community 124 - "._handle_voice_note"
Cohesion: 0.09
Nodes (12): Tests for core.anthropic.extract_text_from_content., Return string content as-is., Return empty string for empty string input., Extract text from a single content block., Concatenate text from multiple content blocks., Skip blocks without text attribute., Skip blocks with empty text., Skip blocks with None text. (+4 more)

### Community 125 - "conftest.py"
Cohesion: 0.11
Nodes (19): pytest_configure(), classify_outcome(), Small JSON report writer for smoke runs., Classify smoke outcomes for triage reports., SmokeOutcome, SmokeReport, format_summary(), Path (+11 more)

### Community 126 - "AuthenticationError"
Cohesion: 0.15
Nodes (17): _directory_mtime_snapshot(), GraphifyProjectWatcher, Path, Background watcher that re-indexes Graphify projects when files change., Return the newest recursive mtime under *root*, skipping noisy dirs.      This i, Poll registered projects and trigger background re-indexing on change., Start the background poll task if it is not already running., Cancel the background poll task and wait for it to finish. (+9 more)

### Community 127 - "EmittedNativeSseTracker"
Cohesion: 0.10
Nodes (9): EmittedBlockState, EmittedNativeSseTracker, Any, Next unused content block index based on emitted starts., Yield ``content_block_stop`` events for blocks that were started but not stopped, Tracked downstream block payload emitted to the client., Close dangling blocks, emit a text error block at a fresh index, then message ta, Parse emitted SSE frames so mid-stream errors can close blocks and pick a fresh (+1 more)

### Community 128 - "ThinkTagParser"
Cohesion: 0.08
Nodes (23): Streaming parser for ``<think>...</think>`` tags.      Handles partial tags at c, Whether currently inside a think tag., ThinkTagParser, Orphan </think> at start should be stripped., Multiple orphan </think> tags should all be stripped., Orphan </think> split across chunks should be stripped., Orphan </think> followed by valid <think>...</think> pair., Empty string input should yield no chunks. (+15 more)

### Community 129 - "freebuff_status.py"
Cohesion: 0.12
Nodes (29): Return the canonical server log path., server_log_path(), candidate_freebuff_base_urls(), fetch_freebuff_health(), fetch_model_count(), format_freebuff_status(), format_seconds(), freebuff_routes() (+21 more)

### Community 130 - "_make_tool_assembler"
Cohesion: 0.15
Nodes (8): unregister_pid(0) is a no-op., Second call to ensure_atexit_registered is idempotent., Exception in os.kill/taskkill is logged but does not raise., register_pid(0) is a no-op (early return)., test_process_registry_ensure_atexit_idempotent(), test_process_registry_kill_all_exception_logged_no_raise(), test_process_registry_register_pid_zero_noop(), test_process_registry_unregister_pid_zero_noop()

### Community 131 - "._format_event"
Cohesion: 0.19
Nodes (11): format_user_error_preview(), get_user_facing_error_message(), Exception, User-facing error formatting shared by API, providers, and integrations., Return a readable, non-empty error message for users.      Known transport and O, Truncate a user-facing error string for short chat replies., DEFAULT_TYPE, Handle /start command. (+3 more)

### Community 132 - "Freebuff2API"
Cohesion: 0.07
Nodes (26): Build from Source, Configuration, Deployment, Disclaimer, Docker, Features, Freebuff2API, Getting Auth Tokens (+18 more)

### Community 133 - "test_feature_manifest.py"
Cohesion: 0.07
Nodes (24): FeatureSource, _create_zai(), Z.ai using Anthropic-compatible Messages at api.z.ai/api/anthropic/v1., ZaiProvider, capability_names(), CapabilityContract, contracted_feature_ids(), Hierarchical public capability map.  This module is the architectural companion (+16 more)

### Community 134 - "Freebuff2API UX Fixes - Loading Delay & Color Issues"
Cohesion: 0.07
Nodes (26): 1. **10-15 Second Loading Delay** ⏱️, 2. **Added Loading Indicator** 🔄, 3. **Unreadable Warning Banner Colors** 🎨, Accessibility, After Fix:, After Fix, `api/admin_static/admin.css`, `api/admin_static/admin.js` (+18 more)

### Community 135 - "parse_sse_text"
Cohesion: 0.14
Nodes (41): format_sse_event(), Format one Anthropic-style SSE event (no logging).      Uses orjson on this hot, parse_sse_text(), _anthropic_interleaved_reasoning_stream(), _anthropic_reasoning_text_stream(), _anthropic_redacted_thinking_stream(), _anthropic_text_stream(), _anthropic_tool_stream() (+33 more)

### Community 136 - "GraphifyProject"
Cohesion: 0.19
Nodes (18): GraphifyProject, BaseModel, One indexed repository known to Graphify., graph_json_path(), Any, Path, Read summary stats from a Graphify project's ``graph.json``.  The full graph can, Return the path to a project's ``graphify-out/graph.json``. (+10 more)

### Community 137 - "Choose A Provider"
Cohesion: 0.10
Nodes (20): 10. [Kimi](https://platform.moonshot.ai/), 11. [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/), 12. [Cerebras Inference](https://inference-docs.cerebras.ai/quickstart), 13. [Groq](https://console.groq.com/), 14. [Fireworks AI](https://fireworks.ai/), 15. [Z.ai](https://z.ai/), 16. [LM Studio](https://lmstudio.ai/), 17. [llama.cpp](https://github.com/ggml-org/llama.cpp) (+12 more)

### Community 138 - "TranscriptBuffer"
Cohesion: 0.20
Nodes (4): Render common Markdown into Discord-compatible format., render_markdown_to_discord(), Tests for render_markdown_to_discord., TestRenderMarkdownToDiscord

### Community 139 - "_SnapshotQueue"
Cohesion: 0.13
Nodes (19): Future, Task, Global Rate Limiter for Messaging Platforms.  Centralizes outgoing message reque, Consume the exception of a completed fire-and-forget task.      Without this cal, Consume the exception of the inner future in ``fire_and_forget``.      The inner, _swallow_future_exception(), _swallow_inner_future_exception(), _swallow_future_exception does nothing when the task succeeded. (+11 more)

### Community 140 - "_test_e2e.py"
Cohesion: 0.15
Nodes (21): _call_tool(), _check(), _cleanup_test_artifacts(), _connect_and_handshake(), main(), _parse_tools_call_result(), Popen, socket (+13 more)

### Community 141 - "Architecture"
Cohesion: 0.11
Nodes (19): Adding A Provider, Architecture, CLI Launchers And Client Adapter Boundary, Configuration Model, Customer-Facing Contract, Design Pressure And Refactor Targets, Graphify MCP Integration, HTTP Request Flow (+11 more)

### Community 142 - "Message"
Cohesion: 0.18
Nodes (13): OpenAIResponsesRequest, BaseModel, Permissive subset of the OpenAI Responses API request shape., create_response(), Create an OpenAI Responses-compatible response through this proxy., FakeProvider, Any, StreamingResponse (+5 more)

### Community 143 - "append_system_directive"
Cohesion: 0.22
Nodes (5): Validate a servers dict. Returns list of error strings (empty = valid)., Validate a remote MCP config's server entries. Returns list of errors., validate_mcp_config(), validate_remote_mcp_config(), TestValidateMcpConfig

### Community 144 - "🤖 Claude Unbound"
Cohesion: 0.11
Nodes (19): 1. Discord And Telegram Bots, 1. Install/Update The Proxy, 2. Start The Proxy, 2. Voice Notes, 3. Graphify Knowledge Graph, 3. Open The Admin UI And Configure NVIDIA NIM, 4. Run Your Coding Agent, 🤖 Claude Unbound (+11 more)

### Community 145 - "ci.sh"
Cohesion: 0.25
Nodes (20): assert_uv_available(), contains_check_id(), fail(), parse_args(), print_command(), quote_arg(), run(), run_check() (+12 more)

### Community 146 - ".reset"
Cohesion: 0.10
Nodes (19): Remove all module contributions from global state (tests only)., add_message_intercepts(), add_reroute_strategies(), get_reroute_strategies(), MessageIntercept, RerouteStrategy, Append intercepts to the runtime message-intercept list., Remove previously appended intercepts (used by tests). (+11 more)

### Community 147 - "TestTreeQueueManager"
Cohesion: 0.24
Nodes (11): format_response_sse_event(), Any, OpenAI Responses SSE event formatting., Format one OpenAI Responses SSE event.      Uses orjson on this hot path; output, _parse(), orjson-backed SSE event formatting stays wire-compatible., test_anthropic_sse_data_is_single_line(), test_anthropic_sse_event_non_ascii_round_trips() (+3 more)

### Community 148 - "input.py"
Cohesion: 0.25
Nodes (18): _append_input_item(), _append_message_item(), _append_pending_reasoning(), _content_as_text(), _convert_message_content(), convert_request_to_anthropic_payload(), _copy_if_present(), _iter_input_items() (+10 more)

### Community 149 - "uninstall.sh"
Cohesion: 0.24
Nodes (19): add_path_entry(), add_uv_to_path(), assert_no_fcc_processes_running(), fail(), is_fcc_command_running(), is_missing_uv_tool_error(), parse_args(), print_command() (+11 more)

### Community 150 - "first_local_provider_model_id"
Cohesion: 0.15
Nodes (19): first_local_provider_model_id(), _first_ollama_model_id(), _first_openai_compatible_model_id(), _get_local_provider_response(), Response, Helpers for local-provider smoke availability checks., Return the first local model id, or skip when the local server is absent., test_llamacpp_models_endpoint_when_available() (+11 more)

### Community 151 - "stream.py"
Cohesion: 0.12
Nodes (13): _make_tool_assembler(), Tests for OpenAI tool-call assembly., Tool call with id starts a tool block., Split-stream tool: id (no name) then name then args; id preserved on start., Argument deltas before tool name are emitted after the block starts., Tool call without id generates a uuid-based id., Task tool with run_in_background=true is forced to false., Chunked Task args are buffered until valid JSON, then forced to false. (+5 more)

### Community 152 - "._on_telegram_voice"
Cohesion: 0.19
Nodes (12): append_system_directive(), _directive_block(), Any, Append a constant system-prompt directive without breaking prefix caches.  Provi, Build a plain text block matching the shape of the existing blocks., Idempotently append ``directive`` to ``request.system`` (in place)., _system_contains(), Any (+4 more)

### Community 153 - "render_markdown_to_discord"
Cohesion: 0.18
Nodes (9): ClientCliAdapter, Any, Protocol, Adapter boundary for client CLI command/env construction and output parsing., Parse one stdout line into parser-ready internal CLI events., Extract a persistent client CLI session id from a parsed event., Return the configured executable name for a wrapper entrypoint., Build the wrapper subprocess command for a client CLI launch. (+1 more)

### Community 154 - "CloudflareAiProvider"
Cohesion: 0.07
Nodes (38): AuthenticationError, OverloadedError, ProviderError, Any, Exception, RateLimitError, Unified exception hierarchy for providers., Convert to Anthropic-compatible error response. (+30 more)

### Community 155 - "request.py"
Cohesion: 0.27
Nodes (16): Google AI Studio Gemini provider (OpenAI-compatible chat completions)., _apply_cached_tool_call_signatures(), _apply_gemini_3_missing_current_turn_signatures(), _apply_gemini_tool_call_signatures(), _apply_thinking_config(), build_request_body(), _current_turn_start_index(), _ensure_dict() (+8 more)

### Community 156 - "test_kimi.py"
Cohesion: 0.20
Nodes (11): _parse_sse_data(), Extract the first JSON object from a Streamable HTTP SSE response body.      The, _free_port(), _graphify_python(), Path, Live smoke test: boot the real ``graphify.serve`` and probe ``/mcp``.  Skips whe, Return a Python interpreter that can ``import graphify``, else None., test_live_graphify_serve_probes_healthy() (+3 more)

### Community 157 - "FakePlatform"
Cohesion: 0.41
Nodes (11): Codec, addSegment(), collectOpenAIContentForCount(), collectOpenAIMessagesForCount(), collectOpenAIResponseFormatForCount(), collectOpenAIToolCallsForCount(), collectOpenAIToolChoiceForCount(), collectOpenAIToolsForCount() (+3 more)

### Community 158 - "session.py"
Cohesion: 0.08
Nodes (38): _codex_model_catalog_config_args(), _fetch_proxy_models_response(), init(), _launch_client_cli(), _load_env_template(), _migrate_legacy_env_if_missing(), _preflight_proxy(), Path (+30 more)

### Community 159 - "stream_state.py"
Cohesion: 0.21
Nodes (12): new_message_item_id(), new_reasoning_item_id(), new_response_id(), Identifier helpers for OpenAI Responses payloads., encrypted_reasoning_item(), message_item(), Any, Responses object and output item builders. (+4 more)

### Community 160 - ".fire_and_forget"
Cohesion: 0.15
Nodes (20): CompletedProcess, Path, Even with kitten on PATH, missing KITTY_LISTEN_ON triggers a guard., FCC_DRY_RUN bypasses the kitten/listen-on checks., FCC_DRY_RUN bypasses the KITTY_LISTEN_ON check., Dry-run with no label prints 'Claude Code' title and correct cwd., Dry-run with a label includes the label in the tab title., Dry-run argv includes `bash` and the path to _claude_tab.sh. (+12 more)

### Community 161 - "OpenAIChatRecovery"
Cohesion: 0.17
Nodes (8): _is_gfm_table_header_line(), normalize_gfm_tables(), Return whether a line looks like a GFM table header., Insert blank lines before detected tables outside fenced code blocks., Tests for _normalize_gfm_tables., Tests for _is_gfm_table_header_line., TestIsGfmTableHeaderLine, TestNormalizeGfmTables

### Community 162 - "Config"
Cohesion: 0.21
Nodes (16): Config, compactStrings(), dedupeStrings(), generateUserAgent(), Duration, loadConfig(), loadRawConfig(), normalizeUpstreamBaseURL() (+8 more)

### Community 163 - "normalize_gfm_tables"
Cohesion: 0.14
Nodes (9): NVIDIA NIM settings (fixed values, no env config)., Any, Set ``body[key]`` only when value is not None., set_if_not_none(), _set_extra(), Tests for providers/nvidia_nim/request.py., TestSetExtra, TestSetIfNotNone (+1 more)

### Community 164 - "OpenAIToolCallAssembler"
Cohesion: 0.18
Nodes (7): OpenAIToolCallAssembler, Assemble OpenAI tool-call deltas into Anthropic SSE tool blocks., Process a single tool-call delta and yield Anthropic SSE events., Emit buffered Task args as a single JSON delta., Emit remaining aliased args without losing malformed JSON., Emit one argument fragment for a started tool block., RecordToolExtraContent

### Community 165 - "test_config_extensibility_product_live.py"
Cohesion: 0.31
Nodes (9): graphify_bin_dir(), graphify_dir(), graphify_venv_dir(), _is_windows(), Path, Filesystem paths for Graphify integration., Return the dedicated Graphify state directory under ~/.fcc., Return the isolated Graphify venv path. (+1 more)

### Community 166 - "Examples"
Cohesion: 0.14
Nodes (14): Admin UI tab, CLI subcommand, Custom messaging platform, Custom token counter, Declared settings, Examples, HTTP middleware, MCP server entry (+6 more)

### Community 167 - "require_api_key"
Cohesion: 0.14
Nodes (24): SSE content_block ``type`` values for Anthropic web server tools (local handlers, assert_anthropic_stream_contract(), event_index(), event_names(), Neutral SSE parsing and Anthropic stream shape assertions.  Used by default CI c, Check minimal Anthropic-style SSE invariants: start/stop, block nesting.      Do, Return the content block ``index`` field from an SSE payload (strict)., text_content() (+16 more)

### Community 168 - "MessagingRateLimiter"
Cohesion: 0.15
Nodes (13): ensure_atexit_registered(), kill_all_best_effort(), kill_pid_tree_best_effort(), Track and clean up spawned CLI subprocesses.  This is a safety net for cases whe, Kill a tracked process and its children where the platform supports it., Kill any still-running registered pids (best-effort)., register_pid(), unregister_pid() (+5 more)

### Community 169 - "test_admin_graphify.py"
Cohesion: 0.22
Nodes (17): client(), _local_client(), _mock_running_manager(), Any, Path, TestClient, Tests for Graphify admin routes., Provide a TestClient with Graphify enabled in cached settings. (+9 more)

### Community 170 - "test_routes_optimizations.py"
Cohesion: 0.13
Nodes (7): mock_settings(), POST /v1/messages/count_tokens with messages: [] matches messages validation., When get_token_count raises, count_tokens returns 500., POST /v1/messages with messages: [] returns 400 invalid_request_error., test_count_tokens_empty_messages_returns_400(), test_count_tokens_error_returns_500(), test_create_message_empty_messages_returns_400()

### Community 171 - "test_uninstallers.py"
Cohesion: 0.33
Nodes (14): _braced_body(), Path, Write mock pgrep/ps that never find running processes.      The uninstaller chec, _repo_root(), _script_text(), _shell_path_with_mock(), test_readme_uninstall_one_liners_use_raw_github_urls(), test_uninstall_sh_fails_when_fcc_commands_are_running() (+6 more)

### Community 172 - "__init__.py"
Cohesion: 0.14
Nodes (4): Deserialize from dictionary., repository(), test_get_pending_children(), test_to_from_dict()

### Community 173 - "GlobalRateLimiter"
Cohesion: 0.18
Nodes (12): APIStatusError, Exception, Retry once with clamped ``max_tokens`` after a context-length 400.          Clou, context_length_clamped_retry_body(), openai_error_text(), Exception, Return a shallow copy of ``body`` with clamped ``max_tokens``, or ``None``., Combine ``str(error)`` with the structured error body when present. (+4 more)

### Community 174 - "TestTreeQueueManager"
Cohesion: 0.15
Nodes (9): Any, Helper to execute a function with exponential backoff on network errors., Edit an existing message., Delete a message from a chat., Delete multiple messages (best-effort)., Enqueue a message edit., Enqueue a message delete., Enqueue a bulk delete (if supported) or a sequence of deletes. (+1 more)

### Community 175 - "AGENTIC DIRECTIVE"
Cohesion: 0.18
Nodes (11): AGENTIC DIRECTIVE, ARCHITECTURE PRINCIPLES, CODING ENVIRONMENT, COGNITIVE WORKFLOW, IDENTITY & CONTEXT, Production files, Required steps, Semver rules (+3 more)

### Community 176 - "provider_catalog.py"
Cohesion: 0.12
Nodes (18): IterStreamChunks, maybe_await_aclose(), Call ``aclose`` on httpx-like responses; ignore sync test doubles., AnthropicMessagesRecovery, Any, Construct recovery events for interrupted native Anthropic streams., Collect text/thinking from an internal native recovery request., AnthropicMessagesStreamRunner (+10 more)

### Community 177 - "app.py"
Cohesion: 0.08
Nodes (26): create_asgi_app(), GracefulLifespanApp, lifespan(), Any, FastAPI, FastAPI application factory and configuration., Create the server ASGI app with graceful lifespan failure reporting., Application lifespan manager. (+18 more)

### Community 178 - "AGENTIC DIRECTIVE"
Cohesion: 0.18
Nodes (11): AGENTIC DIRECTIVE, ARCHITECTURE PRINCIPLES, CODING ENVIRONMENT, COGNITIVE WORKFLOW, IDENTITY & CONTEXT, Production files, Required steps, Semver rules (+3 more)

### Community 179 - "Contributing to `Gelvey/claude-unbound`"
Cohesion: 0.20
Nodes (10): Branch protection on `main`, Contributing to `Gelvey/claude-unbound`, Development setup, Emergency / recovery push to `main`, License, Re-running CI on demand, Routine workflow, Running the full CI locally (+2 more)

### Community 180 - ".__init__"
Cohesion: 0.20
Nodes (9): _configured_env_files(), _env_file_override(), _env_file_value(), Path, Return the currently configured env files for Settings., Return a dotenv value when the file explicitly defines the key., Return the last configured dotenv value that explicitly defines a key., Let explicit .env auth config override stale shell/client tokens. (+1 more)

### Community 181 - "dump_raw_messages_request"
Cohesion: 0.17
Nodes (7): MessagingRateLimiter, Any, Ensure the worker task exists., Background worker that processes queued messaging tasks., Enqueue a messaging task and return its future result.         If dedup_key is p, Enqueue a task without waiting for the result., A thread-safe global rate limiter for messaging.      Uses a custom queue with t

### Community 182 - ".get_actual_status"
Cohesion: 0.09
Nodes (21): config_path(), _find_free_port(), generate_config(), Any, Path, Generate Freebuff2API config.json from credentials and settings.  The config for, Return the default config file path., Read the port from the existing config file, or None if not found. (+13 more)

### Community 184 - "test_process_registry.py"
Cohesion: 0.21
Nodes (12): admin_launch_message(), _browser_host_for_local_urls(), local_admin_url(), local_proxy_root_url(), Helpers for presenting local admin URLs., Return the proxy root URL (no path) for clients on the same machine., Return a browser-friendly URL for the localhost-only admin UI., Return the startup message shown by supported launch commands. (+4 more)

### Community 185 - "_provider"
Cohesion: 0.02
Nodes (73): CLISession, Any, Protocol, Protocol for CLI session - avoid circular import from cli package., Execute a coroutine without awaiting it., Protocol for session managers to avoid tight coupling with cli package.      Imp, Get an existing session or create a new one.          Returns: Tuple of (session, Register the real session ID from CLI output. (+65 more)

### Community 186 - "UpstreamClient"
Cohesion: 0.31
Nodes (6): Client, Context, Duration, UpstreamClient, Response, retryAfterDuration()

### Community 188 - "Extension Checklists"
Cohesion: 0.29
Nodes (7): Add A Client Adapter, Add A Custom Module, Add A Messaging Platform, Add An Admin Setting, Add Or Change Graphify Behavior, Add Protocol Behavior, Extension Checklists

### Community 189 - "RuntimeError"
Cohesion: 0.17
Nodes (5): Lazy tiktoken encoder: no BPE load at import time, cached on first use., A fresh interpreter importing tokens must not load the encoder., TestGetEncoder, TestImportTimeLaziness, TestSseEncoderFallback

### Community 190 - "Custom Modules for Claude Unbound"
Cohesion: 0.29
Nodes (7): Builder API, Custom Modules for Claude Unbound, Loading and failure handling, Module contract, Quick start, Troubleshooting, Where to put modules

### Community 191 - "test_ci_scripts.py"
Cohesion: 0.33
Nodes (10): _path_without_uv(), Path, _repo_root(), _script_text(), _shell_interpreter(), test_ci_sh_dry_run_does_not_require_uv(), test_ci_sh_fail_fast_runs_checks_sequentially(), test_ci_sh_is_tracked_executable() (+2 more)

### Community 192 - ".feed"
Cohesion: 0.27
Nodes (7): Any, Cerebras Inference provider (OpenAI-compatible chat completions)., build_request_body(), _normalize_max_completion_tokens(), Any, Request builder for Cerebras Inference (OpenAI-compatible chat completions).  Do, Build OpenAI-format request body from an Anthropic request for Cerebras.

### Community 193 - "test_model_listing.py"
Cohesion: 0.25
Nodes (8): get_module_token_counter(), TokenCounter, Override the request token counter (last-registered wins)., Clear the module-supplied token counter (used by tests)., Return the module-supplied token counter, or None if none registered., reset_module_token_counter(), set_module_token_counter(), ProviderGetter

### Community 194 - "AnthropicSseEvent"
Cohesion: 0.27
Nodes (9): AnthropicSseEvent, iter_sse_events(), parse_sse_event(), Any, Anthropic SSE parsing used by the Responses stream adapter., iter_responses_sse_from_anthropic(), Any, Translate Anthropic SSE streams into OpenAI Responses SSE streams. (+1 more)

### Community 195 - "_cf_models_payload"
Cohesion: 0.22
Nodes (7): Tests for extract_text_from_content helper functions., extract_text_from_content handles whitespace-only string., extract_text_from_content handles unicode content., Parametrized scalar and empty input handling., test_extract_functions_unicode(), test_extract_functions_whitespace_only(), test_extract_text_scalar_and_empty_parametrized()

### Community 196 - ".convert_system_prompt"
Cohesion: 0.12
Nodes (18): _append_event(), parse_sse_lines(), SSEEvent, assistant_content_from_events(), ConversationTurn, default_cli_events(), FakeCLIManager, FakeCLISession (+10 more)

### Community 197 - "module_settings.py"
Cohesion: 0.33
Nodes (5): Limitations, Overriding the repo path, Spawn Claude Code Tab, Troubleshooting, Usage

### Community 198 - "ensureFreebuffSystemMarker"
Cohesion: 0.49
Nodes (9): ensureFreebuffSystemMarker(), countSystemMessages(), T, TestEnsureFreebuffSystemMarkerMergesIntoArraySystemMessage(), TestEnsureFreebuffSystemMarkerMergesIntoStringSystemMessage(), TestEnsureFreebuffSystemMarkerNoopWhenMarkerPresent(), TestEnsureFreebuffSystemMarkerNoopWhenNoMessages(), TestEnsureFreebuffSystemMarkerPrependsStandaloneWhenAbsent() (+1 more)

### Community 199 - "_parse_allowed_channels"
Cohesion: 0.14
Nodes (10): Telegram Platform Adapter  Implements MessagingPlatform for Telegram using pytho, PendingVoiceRegistry, Path, Platform-neutral voice note helpers., Track voice notes that are still waiting on transcription., Run configured transcription backends off the event loop., VoiceTranscriptionService, test_pending_voice_registry_complete_removes_entries() (+2 more)

### Community 200 - "test_voice_handlers.py"
Cohesion: 0.18
Nodes (10): Tests for voice note handling in Telegram and Discord platforms., When voice_note_enabled is False, reply with disabled message., When voice_note_enabled is False, reply with disabled message., Voice from unauthorized user is ignored (no reply)., Successful transcription invokes message handler with transcribed text., telegram_platform(), test_discord_voice_disabled_sends_reply(), test_telegram_voice_disabled_sends_reply() (+2 more)

### Community 201 - "test_mcp_proxy.py"
Cohesion: 0.22
Nodes (6): Graphify MCP tool metadata for per-session project routing.  Claude Unbound tags, Tests for Graphify MCP tool metadata used by the project-routing directive.  ``G, ``affected`` is a graphify CLI command, not an exposed MCP tool., Regression guards for tools the old set was missing., test_graphify_tool_names_cover_neighbor_and_pr_tools(), test_graphify_tool_names_exclude_nonexistent_affected()

### Community 202 - "Connect Your Client"
Cohesion: 0.33
Nodes (6): 1. Claude Code CLI, 2. Codex CLI, 3. Claude Code in VS Code, 4. Codex in VS Code, 5. Claude Code in JetBrains ACP, Connect Your Client

### Community 203 - "Development"
Cohesion: 0.33
Nodes (6): 1. Project Structure, 2. Run From Source, 3. Commands, 4. Package Scripts, 5. Extending, Development

### Community 204 - "ContentChunk"
Cohesion: 0.24
Nodes (6): ContentChunk, Parse content inside think tags., Flush any remaining buffered content., A chunk of parsed content., Feed content and yield parsed chunks., Parse content outside think tags.

### Community 205 - "TestTransportHeaderMerge"
Cohesion: 0.03
Nodes (79): decode_gateway_model_id(), DecodedGatewayModelId, gateway_model_id(), no_thinking_gateway_model_id(), Gateway-safe model id encoding for Claude Code model discovery., Return the normal Claude Code-discoverable id for a provider/model ref., Return a Claude Code-discoverable id that disables client thinking., Decode a model id advertised by this gateway, if it is one. (+71 more)

### Community 206 - "ContentType"
Cohesion: 0.06
Nodes (40): ProviderConfig, BaseModel, Configuration for a provider.      Base fields apply to all providers. Provider-, DeepSeekProvider, Response, DeepSeek provider implementation (native Anthropic-compatible Messages)., DeepSeek using ``https://api.deepseek.com/anthropic`` (Anthropic Messages API)., DeepSeek lists models from the OpenAI-format root, not /anthropic. (+32 more)

### Community 207 - "build_rendering_profile"
Cohesion: 0.39
Nodes (6): build_rendering_profile(), Platform rendering profiles for messaging transcripts and status text., Return rendering rules for a messaging platform., RenderingProfile, test_discord_rendering_profile_has_plain_parse_mode(), test_telegram_rendering_profile_uses_markdown_v2()

### Community 208 - "._create_transcript_and_render_ctx"
Cohesion: 0.20
Nodes (11): ModuleError, ModuleLoadError, ModuleRegistrationError, Exception, Errors raised by the custom module loader., Raised when a module cannot be discovered or imported., Raised when a module's registration into a runtime surface fails., Base exception for module system errors. (+3 more)

### Community 210 - "register_messaging_platform"
Cohesion: 0.67
Nodes (3): Register a messaging platform factory (used by custom modules)., register_messaging_platform(), _PlatformFactory

### Community 212 - ".set_current_task"
Cohesion: 0.29
Nodes (4): Any, Internal helper for tests and shared building., Strip private request metadata before calling NVIDIA NIM., Return NIM tool argument aliases captured while building this request.

### Community 214 - "test_orphan_close_tag_at_end"
Cohesion: 0.32
Nodes (3): Any, Flush any remaining tool call in the buffer., Feed text and return safe text plus detected tool calls.

### Community 215 - "writeClaudeStreamingResponse"
Cohesion: 0.29
Nodes (6): graphify_settings(), graphify_tmp_home(), Path, Fixtures for Graphify tests., Redirect ~/.fcc and HOME to a temporary directory for the test., Return Settings with Graphify enabled and deterministic values.

### Community 216 - "start_mcp.sh"
Cohesion: 0.47
Nodes (4): PATH, start_mcp.sh script, _timeout(), wait_for_health()

### Community 217 - "writeClaudeStreamingResponse"
Cohesion: 0.33
Nodes (3): Initialize and connect to Telegram., Send a message to a chat., Enqueue a message to be sent (using limiter).

### Community 218 - ".on_shutdown"
Cohesion: 0.40
Nodes (3): FastAPI, Register a startup hook., Register a shutdown hook.

### Community 219 - ".edit_message"
Cohesion: 0.40
Nodes (4): Path, Regression for ``api.app.general_error_handler`` settings-reload guard.  Bug his, ``SettingsError`` raised by ``get_settings()`` does NOT re-trigger the handler., test_general_error_handler_emits_clean_500_when_settings_reload_raises()

### Community 221 - "test_openrouter_free_model_ids_handles_common_shapes"
Cohesion: 0.33
Nodes (5): _extract_input_tokens(), _extract_limit_and_input_tokens(), Clamp ``max_tokens`` after OpenAI-style context-length 400 errors.  Some upstrea, Return ``(context_limit, input_tokens)`` parsed from a context error., OpenAI-compatible chat transport family.

### Community 222 - "launcher.sh"
Cohesion: 0.43
Nodes (6): activate_window(), color_tab(), notify(), launcher.sh script, spawn_tab(), wait_for_socket()

### Community 223 - "mcp_proxy_tool.py"
Cohesion: 0.80
Nodes (4): _connect(), main(), socket, _relay()

### Community 224 - "_verify_launcher.py"
Cohesion: 0.80
Nodes (4): cleanup(), main(), start_launcher(), wait_for_self_test_line()

### Community 226 - "test_freebuff_binary_manager.py"
Cohesion: 0.50
Nodes (4): Path, Tests for Freebuff2API binary/image lifecycle helpers., test_build_patched_docker_image_rebuilds_stale_patch_image(), test_build_patched_docker_image_reuses_current_patch_image()

### Community 229 - "tools.py"
Cohesion: 0.67
Nodes (3): ParserState, Enum, Heuristic parser for text-emitted tool calls.

### Community 259 - ".__init__"
Cohesion: 0.17
Nodes (15): _build_model(), get_module_settings(), _module_env_files(), Any, BaseSettings, Dynamic Settings model built from module-declared fields.  Each module that want, Return the current ``ModuleSettings`` instance.      The instance is rebuilt on, Dotenv files the dynamic ModuleSettings reads from, as plain strings. (+7 more)

### Community 262 - ".convert_tools"
Cohesion: 0.40
Nodes (4): _tool_input_schema(), MockTool, test_convert_tool_without_input_schema_uses_empty_object_schema(), test_convert_tools()

### Community 295 - "ContentType"
Cohesion: 0.50
Nodes (4): ContentType, Enum, Streaming parser for provider-emitted thinking tags., Type of content chunk.

### Community 299 - "writeClaudeStreamingResponse"
Cohesion: 0.67
Nodes (6): Response, ResponseWriter, writeClaudeNonStreamResponse(), writeClaudeSSEEvents(), writeClaudeStreamingResponse(), writeClaudeSuccessResponse()

### Community 300 - ".mcp_server"
Cohesion: 0.40
Nodes (3): Any, Declare a Settings field that this module reads., Register an MCP server backend (added to mcp_config.json on next write).

### Community 319 - "optimization_handlers.py"
Cohesion: 0.33
Nodes (4): Neutral provider catalog: IDs, credentials, defaults, proxy and capability metad, Freeze ``PROVIDER_CATALOG`` insertion order used as canonical provider ranking., NIM first; DeepSeek fourth; Wafer ninth / Kimi tenth; cloudflare_ai after cerebr, test_provider_catalog_key_order_matches_canonical_plan()

## Knowledge Gaps
- **273 isolated node(s):** `github.com/Quorinex/Freebuff2API`, `state`, `mcpState`, `freebuffState`, `graphifyState` (+268 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **84 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Settings` to `freebuff_status.py`, `test_web_server_tools.py`, `MessagesRequest`, `ProviderRegistry`, `test_feature_manifest.py`, `SmokeConfig`, `registry.py`, `admin_routes.py`, `Message`, `claude_cli_matrix.py`, `NimSettings`, `MessagingPlatform`, `runtime.py`, `entrypoints.py`, `test_cloudflare_ai.py`, `._on_telegram_voice`, `ClaudeMessageHandler`, `test_entrypoints.py`, `session.py`, `Module`, `is_prefix_detection_request`, `admin_config.py`, `test_routes_optimizations.py`, `ModelListResponseError`, `app.py`, `test_dependencies.py`, `GraphifyManager`, `.__init__`, `test_process_registry.py`, `_provider`, `OllamaProvider`, `test_manager.py`, `test_model_listing.py`, `codex.py`, `loader.py`, `test_llamacpp.py`, `TestTransportHeaderMerge`, `ContentType`, `Path`, `LMStudioProvider`, `test_adapters.py`, `writeClaudeStreamingResponse`, `.on_shutdown`, `test_admin.py`, `optimization_handlers.py`, `test_smoke_config.py`, `test_long_context_fallback.py`, `_JsonResponse`, `test_groq.py`, `test_codestral.py`, `configure_logging`, `test_cerebras.py`, `test_mistral.py`, `PendingVoiceRegistry`?**
  _High betweenness centrality (0.199) - this node is a cross-community bridge._
- **Why does `trace_event()` connect `trace_event` to `test_web_server_tools.py`, `TestExtractTextFromContent`, `stream_recovery.py`, `MessagingRateLimiter`, `SessionStore`, `StreamRecoverySession`, `TestTransportHeaderMerge`, `format_sse_event`, `CLISession`, `ModelListResponseError`, `app.py`, `create_app`, `provider_catalog.py`, `test_modules.py`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Why does `ProviderConfig` connect `ContentType` to `MessagesRequest`, `ProviderRegistry`, `test_feature_manifest.py`, `registry.py`, `Message`, `TestProviderRateLimiter`, `_make_provider`, `NimSettings`, `test_freebuff.py`, `test_cloudflare_ai.py`, `CloudflareAiProvider`, `request.py`, `SSEEvent`, `request.py`, `normalize_gfm_tables`, `ModelListResponseError`, `NvidiaNimProvider`, `InvalidRequestError`, `_provider`, `OllamaProvider`, `.feed`, `test_gemini.py`, `base.py`, `test_llamacpp.py`, `TestTransportHeaderMerge`, `test_open_router.py`, `LMStudioProvider`, `request.py`, `optimization_handlers.py`, `test_long_context_fallback.py`, `test_groq.py`, `map_error`, `test_codestral.py`, `stable_session_key`, `test_cerebras.py`, `test_mistral.py`, `extract_provider_stream_usage`, `test_context_length_clamp.py`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._
- **Are the 66 inferred relationships involving `Settings` (e.g. with `ConfigFieldSpec` and `ConfigSectionSpec`) actually correct?**
  _`Settings` has 66 INFERRED edges - model-reasoned connections that need verification._
- **Are the 62 inferred relationships involving `MessagesRequest` (e.g. with `AdminTabSpec` and `Module`) actually correct?**
  _`MessagesRequest` has 62 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `SmokeConfig` (e.g. with `Settings` and `SmokeOutcome`) actually correct?**
  _`SmokeConfig` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 41 inferred relationships involving `Message` (e.g. with `TestPrivateAttrPropagation` and `TestRouteCapture`) actually correct?**
  _`Message` has 41 INFERRED edges - model-reasoned connections that need verification._