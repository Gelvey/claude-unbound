# Custom Modules for Claude Unbound

Claude Unbound can load user-supplied Python modules at startup. Modules can add
capabilities without modifying the core repository: new providers, custom routes,
request-pipeline hooks, optimization handlers, messaging platforms, and
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
```

## Module contract

A module is a top-level `.py` file or a package directory with an
`__init__.py`. Claude Unbound ignores files and packages whose names start with
`_` and the `__pycache__` directory.

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

async def startup(app, settings):
    print("Module is starting")

async def shutdown(app, settings):
    print("Module is shutting down")

@router.get("/ping")
def ping():
    return {"ok": True}

def setup_module(app, settings):
    return (
        Module(name="lifecycle_demo")
        .router(router)
        .on_startup(startup)
        .on_shutdown(shutdown)
    )
```

## Builder API

`api.modules.module(name)` returns a `Module` with a fluent API:

| Method | Purpose |
|---|---|
| `.provider(provider_id, descriptor, factory)` | Register a new provider |
| `.router(router)` | Include a FastAPI `APIRouter` |
| `.intercept(fn)` | Register a message intercept |
| `.optimizer(fn)` | Register an optimization handler |
| `.messaging_platform(name, factory)` | Register a messaging platform factory |
| `.on_startup(fn)` | Run async code during server startup |
| `.on_shutdown(fn)` | Run async code during server shutdown |

## Examples

### Register a custom provider

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
        # implementation
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

The provider will appear in admin UI provider lists and can be referenced in
model refs like `my_provider/...`.

### Message intercept

```python
from api.modules import Module

async def add_system_role(routed_request):
    # Return a modified object or None to keep the request unchanged.
    return None

FCC_MODULE = Module(name="interceptor").intercept(add_system_role)
```

### Optimization handler

```python
from api.models.responses import MessagesResponse
from api.modules import Module

async def skip_pong(request_data, settings):
    if request_data.messages[-1].content == "ping":
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
    async def start(self):
        ...

    async def stop(self):
        ...

    async def send_message(self, *args, **kwargs):
        ...

def make_slack(options):
    return SlackPlatform(options)

FCC_MODULE = Module(name="slack_bridge").messaging_platform(
    "slack", make_slack
)
```

Then set `MESSAGING_PLATFORM=slack` in `.env`.

## Loading and failure handling

Modules are loaded alphabet order. If a module fails to import or register, an
error is logged and the server continues starting up. Module code runs with the
same privileges as the Claude Unbound server, so only install modules you trust.

## Troubleshooting

- Set `FCC_LOG_LEVEL=DEBUG` to see which modules were discovered.
- A module does not appear: check that the file name does not start with `_` and
  that the directory is configured with `FCC_MODULES_DIR`.
- A provider added by a module is rejected: ensure the provider descriptor
  includes all required fields and that the factory signature matches
  `BaseProvider`.
