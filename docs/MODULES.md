# Custom Modules for Claude Unbound

Claude Unbound can load user-supplied Python modules at startup. Modules can add
or change almost every surface of the server without modifying the core
repository: new providers, custom routes, request-pipeline hooks, optimization
handlers, messaging platforms, HTTP middlewares, token counters, reroute
strategies, system-prompt directives, admin UI tabs, typed settings fields,
CLI subcommands, MCP server backends, trace-event listeners, and
startup/shutdown lifecycle code.

## Where to put modules

Default directory:

```text
~/.fcc/modules/
```

Override with environment variables:

```bash
FCC_MODULES_ENABLED=true          # default true
FCC_MODULES_DIR=/path/to/modules  # default ~/.fcc/modules
FCC_MODULES_STRICT=false          # default false; true makes module startup hook failures fatal
```

These are read by the module loader, **not** by `config.settings.Settings`,
because module registration runs before `Settings()` is built (so module-registered
provider ids are part of the model's validation).

## Module contract

A module is a top-level `.py` file or a package directory with an
`__init__.py`. Claude Unbound ignores files and packages whose names start with
`_` and the `__pycache__` directory.

> **Multi-file packages:** submodule files inside a package directory are **not**
> auto-imported. The package's `__init__.py` must `import` any helper files it
> needs, or they will not be visible.

Each module must expose **one** of the following:

- A module-level object named `FCC_MODULE`.
- A top-level function named `setup_module(app, settings)` that returns a module
  object.

Both must return an instance of `api.modules.Module`.

## Quick start

Create `~/.fcc/modules/hello.py`:

```python
from api.modules import module
from fastapi import APIRouter

router = APIRouter()

@router.get("/hello")
def hello():
    return {"hello": "module"}

FCC_MODULE = module("hello").router(router)
```

Restart the server and visit `http://localhost:8082/hello`.

A module can also be built with the `setup_module` hook:

```python
from api.modules import Module
from fastapi import APIRouter

router = APIRouter()

@router.get("/ping")
def ping():
    return {"ok": True}

async def startup(app, settings):
    print("Module is starting")

async def shutdown(app, settings):
    print("Module is shutting down")

def setup_module(app, settings):
    return (
        Module(name="lifecycle_demo")
        .router(router)
        .on_startup(startup)
        .on_shutdown(shutdown)
    )
```

## Builder API

`api.modules.module(name)` and `api.modules.Module(name)` return a `Module` with
a fluent API. Every method returns `self` so calls can be chained.

| Method | Purpose |
|---|---|
| `.provider(provider_id, descriptor, factory)` | Register a new provider (descriptor + factory are both required) |
| `.router(router)` | Include a FastAPI `APIRouter` |
| `.middleware(middleware_class)` | Add a Starlette/FastAPI HTTP middleware (wraps the trace middleware) |
| `.intercept(fn)` | Register a message intercept; return a `StreamingResponse` to short-circuit |
| `.optimizer(fn)` | Register an optimization handler |
| `.reroute(fn)` | Rewrite a routed request before provider dispatch |
| `.system_directive(text)` | Append a constant system-prompt directive to every request |
| `.token_counter(fn)` | Override the request token counter (last-registered wins) |
| `.messaging_platform(name, factory)` | Register a messaging platform factory |
| `.admin_tab(id, label, title, html, mount_js=None)` | Add a tab to the admin UI |
| `.setting(alias, type, default=..., description="")` | Declare a typed Settings field read from `.env` |
| `.cli_command(name, help, handler)` | Register a CLI subcommand (`fcc <name>`) |
| `.mcp_server(name, backend)` | Add an MCP server entry to `mcp_config.json` |
| `.trace_listener(fn)` | Receive every structured trace event |
| `.on_startup(fn)` | Run async code during server startup |
| `.on_shutdown(fn)` | Run async code during server shutdown |

## Examples

### Register a custom provider

Both a descriptor and a factory are required; if either is missing the
registration is rejected as a whole so `PROVIDER_CATALOG` and
`PROVIDER_FACTORIES` never diverge.

```python
from api.modules import Module
from config.provider_catalog import ProviderDescriptor
from providers.base import BaseProvider, ProviderConfig
from config.settings import Settings

class MyProvider(BaseProvider):
    def __init__(self, config: ProviderConfig, settings: Settings):
        self.config = config
        self.settings = settings

    async def stream_messages(self, request):
        ...

def my_factory(config: ProviderConfig, settings: Settings) -> BaseProvider:
    return MyProvider(config, settings)

descriptor = ProviderDescriptor(
    provider_id="my_provider",
    transport_type="openai_chat",
    capabilities=("tool_use",),
)

FCC_MODULE = Module(name="my_provider").provider(
    "my_provider", descriptor, my_factory
)
```

### HTTP middleware

Module middlewares are added *after* Claude Unbound's built-in trace
middleware, so they wrap it (i.e. an auth-checking module middleware runs
*before* the trace middleware binds the request id to logs).

```python
from api.modules import Module
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

class RequireApiKey(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.headers.get("X-My-Key") != "secret":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

FCC_MODULE = Module(name="auth").middleware(RequireApiKey)
```

### Message intercept (short-circuit with a response)

Intercepts run in registration order. Returning a non-`None` value short-circuits
the rest of the pipeline — return a `StreamingResponse`, `JSONResponse`, or any
FastAPI response object to serve a custom response without calling the provider.

```python
from fastapi.responses import JSONResponse
from api.modules import Module

async def maybe_handle_locally(routed_request):
    if routed_request.request.messages[-1].content == "ping":
        return JSONResponse({"reply": "pong"})
    return None  # pass through to the provider

FCC_MODULE = Module(name="interceptor").intercept(maybe_handle_locally)
```

### Reroute strategy

Reroutes run after the model is resolved but before the long-context fallback.
Return a `RoutedMessagesRequest` to rewrite the destination, or `None` to leave
the request unchanged. Multiple reroutes compose — each one runs against the
previous result.

```python
from api.modules import Module
from api.request_pipeline import RoutedMessagesRequest

def reroute_to_local(routed, settings):
    if "local" in (routed.request.system or ""):
        from api.model_router import ModelRouter
        from config.settings import get_settings
        resolved = ModelRouter(get_settings()).resolve("local/llama-3.1-8b")
        return RoutedMessagesRequest(
            request=routed.request, resolved=resolved
        )
    return None

FCC_MODULE = Module(name="local_reroute").reroute(reroute_to_local)
```

### System directive

Append a constant system-prompt fragment to every Messages request. Useful for
project-wide house style, compliance footers, or persona overrides. Directives
are appended (cache-safe) — they do not invalidate prompt-cache.

```python
from api.modules import Module

DIRECTIVE = (
    "Project: Acme. Style: terse, no preamble. "
    "Always end with a 'references:' section."
)

FCC_MODULE = Module(name="acme_style").system_directive(DIRECTIVE)
```

### Custom token counter

Replace the request token counter. Last-registered wins; modules may wrap the
default to compose.

```python
from api.modules import Module

def my_counter(messages, system, tools):
    return sum(len(m.get("content", "")) for m in messages) // 4

FCC_MODULE = Module(name="estimate").token_counter(my_counter)
```

### Admin UI tab

Add a tab to the admin UI. The tab is served by
`GET /admin/api/modules/tabs` and mounted dynamically by the admin frontend.
`mount_js` runs in a scoped `Function` after the tab's HTML is inserted.

```python
from api.modules import Module

HTML = """
<div class="module-section">
  <h3>My Module</h3>
  <p id="module-status">Loading...</p>
</div>
"""

JS = """
const el = document.getElementById("module-status");
el.textContent = "Loaded at " + new Date().toISOString();
"""

FCC_MODULE = Module(name="my_tab").admin_tab(
    id="my_module",
    label="My Module",
    title="My Module diagnostic view",
    html=HTML,
    mount_js=JS,
)
```

### Declared settings

Add a typed field to the dynamic `ModuleSettings` model. The loader collects
all declared fields after `load_for_app` and builds a single
`pydantic_settings.BaseSettings` subclass via `pydantic.create_model`. The
model reads the same dotenv files as the main `Settings`, so a module's
`MY_PLUGIN_API_KEY` is configured in `~/.fcc/.env` like any other setting.

```python
from api.modules import Module, ModuleSettingSpec

FCC_MODULE = Module(name="my_plugin").setting(
    alias="MY_PLUGIN_API_KEY",
    type=str,
    default="",
    description="API key for the My Plugin backend.",
)
```

The active model is read with `config.module_settings.get_module_settings()`.

### CLI subcommand

Register a CLI subcommand invoked as `fcc <name> [args...]`. The handler
receives the remaining argv (without the subcommand name) and returns a
process exit code.

```python
from api.modules import Module, ModuleCliCommand

def mycmd(argv):
    print("ran with", argv)
    return 0

FCC_MODULE = Module(name="my_cli").cli_command(
    name="mycmd",
    help="Run a one-off diagnostic",
    handler=mycmd,
)
```

`fcc mycmd foo bar` prints `ran with ['foo', 'bar']` and exits 0. Run
`fcc` with no arguments to see all built-in + module-registered subcommands.

### MCP server entry

Register an MCP backend. The next admin UI save persists the entry to
`mcp_config.json`, and the MCP router picks it up on restart. (This is a
*config-time* hook — modules that need full in-process MCP server lifecycle
should talk to the MCP router via its existing JSON-RPC socket patterns.)

```python
from api.mcp_config import McpBackend
from api.modules import Module, ModuleMcpServer

backend = McpBackend(
    name="my_tool",
    type="stdio",
    port=19001,
    command="python",
    args=["-m", "my_module.mcp_server"],
)

FCC_MODULE = Module(name="my_mcp").mcp_server(
    name="my_tool", backend=backend
)
```

### Trace listener

Receive every structured trace event (`stage`, `event`, `source`, `fields`).
Listeners are best-effort: errors are logged but never propagated.

```python
from api.modules import Module

events = []

def listener(stage, event, source, fields):
    events.append((stage, event, source))

FCC_MODULE = Module(name="audit").trace_listener(listener)
```

### Optimization handler

Optimization handlers short-circuit the request when they can serve a response
without calling the provider. Returning `None` keeps the request flowing.

```python
from api.models.responses import MessagesResponse
from api.modules import Module

async def skip_pong(request_data, settings):
    if request_data.messages and request_data.messages[-1].content == "ping":
        return MessagesResponse(
            id="msg_pong",
            model=request_data.model,
            content=[{"type": "text", "text": "pong"}],
            stop_reason="end_turn",
        )
    return None

FCC_MODULE = Module(name="pinger").optimizer(skip_pong)
```

### Custom messaging platform

```python
from api.modules import Module
from messaging.platforms.base import MessagingPlatform

class SlackPlatform(MessagingPlatform):
    async def start(self): ...
    async def stop(self): ...
    async def send_message(self, *args, **kwargs): ...

def make_slack(options):
    return SlackPlatform(options)

FCC_MODULE = Module(name="slack_bridge").messaging_platform("slack", make_slack)
```

Then set `MESSAGING_PLATFORM=slack` in `.env`.

## Loading and failure handling

Modules are loaded in alphabetical order. If a module fails to import or
register, an error is logged and the server continues starting up. Set
`LOG_API_ERROR_TRACEBACKS=true` to get full tracebacks for module load
failures (the same flag also enables tracebacks for the rest of the app).

Module code runs with the same privileges as the Claude Unbound server, so
only install modules you trust.

## Troubleshooting

- Set `LOG_LEVEL=DEBUG` to see which modules were discovered.
- A module does not appear: check that the file name does not start with `_`,
  that `__init__.py` is present for package directories, and that the
  directory is configured with `FCC_MODULES_DIR`.
- A provider added by a module is rejected: ensure the provider descriptor
  includes all required fields and that the factory signature matches
  `BaseProvider`. Both descriptor and factory must be supplied together.
- Multi-file package helpers are not visible: `__init__.py` must `import` them
  explicitly; the loader does not auto-import sibling files.
