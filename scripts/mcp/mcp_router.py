"""
MCP Meta-Router — on-demand activation of backend MCP servers.

Architecture
------------
- One `supergateway` process per stdio backend exposes it as HTTP/SSE
  on http://127.0.0.1:<port>/sse. Lifecycle owned by start_mcp.sh.
- For `type: sse` backends (remote), no supergateway is spawned; the
  router connects directly to the configured URL.
- This router is a single persistent Unix-socket daemon. It is the only
  entry point that Claude Code talks to. (Claude Code invokes it via
  `mcp-proxy-tool -p <socket>`, which speaks JSON-RPC over the socket
  directly to this process.) One router process handles ALL client
  connections — there is no per-connection fork.
- On startup, this router advertises ONLY control tools:
      list_servers, use_server, list_active_servers, deactivate_server
- When the LLM calls `use_server("stripe")`, this router opens an SSE
  client session to the backend, calls initialize+tools/list, and
  dynamically registers those tools under its own namespace
  (`<backend>__<tool>`). The response tells the LLM to call
  `tools/list` next so its view of available tools refreshes.
- When the LLM calls an activated tool, the router forwards `tools/call`
  to the matching backend session and relays the response.

The router keeps each backend's tools prefixed with a spec-safe slug
derived from the backend name (e.g. `composio__get_version`, or
`shared_growthbook__get_projects` for a shared backend whose display
name is `[shared] growthbook`) to avoid collisions across backends that
may share tool names. MCP tool names must match `^[a-zA-Z0-9_-]{1,64}$`,
so the `[shared] ` display prefix is stripped to `shared_` and any other
non-safe char is replaced with `_` before it appears on the wire.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import anyio
import httpx
from mcp import ClientSession, types
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.server import Server
from mcp.shared.message import SessionMessage

log = logging.getLogger("mcp-router")

# Set by ``main()`` from the --config argument so reloads load the same file.
_CONFIG_PATH: Path | None = None

# Canonical config path is ~/.fcc/mcp_config.json, matching the ~/.fcc/.env
# pattern. Overridable via MCP_ROUTER_CONFIG env var for testing or custom setups.
CONFIG_PATH = Path(
    os.environ.get(
        "MCP_ROUTER_CONFIG",
        str(Path.home() / ".fcc" / "mcp_config.json"),
    )
)


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------


class Backend:
    """A configured backend (one entry from mcp_config.json's `servers` map)."""

    def __init__(self, name: str, cfg: dict[str, Any]) -> None:
        self.name = name
        # Spec-safe prefix used to build advertised tool names. MCP tool
        # names must match ^[a-zA-Z0-9_-]{1,64}$; the display `name` for
        # shared backends is "[shared] <name>" which contains brackets
        # and a space, so it can't be used directly in a tool name. We
        # keep `name` for list_servers/use_server (human-readable) and
        # use `tool_prefix` for the wire tool name (e.g. shared_growthbook
        # -> shared_growthbook__get_projects).
        self.tool_prefix = _tool_prefix(name)
        self.cfg = cfg
        if cfg.get("url"):
            self.url = cfg["url"]
        elif cfg.get("type") == "http":
            self.url = f"http://127.0.0.1:{cfg['port']}/mcp"
        else:
            self.url = f"http://127.0.0.1:{cfg['port']}/sse"
        # tools registered by this backend (filled in on activation)
        self.tools: dict[str, types.Tool] = {}
        # active client session (kept open for tool-call forwarding).
        # Owned by a long-lived ``_session_owner`` task running in the
        # router's event loop — NOT inside any client connection's task
        # group. The MCP SSE/HTTP client spawns a background reader task
        # when its context manager is entered; if that ``__aenter__`` runs
        # inside a connection's ``anyio.create_task_group()`` (as it did
        # before), the reader is parented to that connection's cancel
        # scope and dies when the connection closes, leaving the session's
        # write stream closed (``anyio.ClosedResourceError`` on the next
        # ``call_tool``) and crashing the connection's task group on
        # teardown ("Attempted to exit a cancel scope that isn't the
        # current tasks's current cancel scope"). The owner task keeps
        # the session alive across connections; see ``_activate``.
        self._session: ClientSession | None = None
        # serialise concurrent use_server() calls for the same backend
        self._activate_lock = asyncio.Lock()
        # serialise concurrent tools/call forwards to the same backend
        # (the MCP ClientSession handles one request at a time)
        self._call_lock = asyncio.Lock()
        # control handles for the running _session_owner task, set
        # together by _activate and cleared by _deactivate / owner finally
        self._shutdown: asyncio.Event | None = None
        self._owner_done: asyncio.Future | None = None
        self._owner_task: asyncio.Task | None = None

    def __repr__(self) -> str:
        return f"Backend({self.name}, url={self.url}, tools={len(self.tools)})"


SHARED_PREFIX = "[shared] "


def _tool_prefix(name: str) -> str:
    """Build a spec-safe tool-name prefix from a backend display name.

    MCP tool names must match ``^[a-zA-Z0-9_-]{1,64}$``. Shared backends
    are registered under the display name ``[shared] <name>`` (brackets +
    space are invalid in tool names), so strip the display prefix and
    replace every remaining non-``[A-Za-z0-9_-]`` char with ``_``,
    collapsing runs so no ``__`` sneaks in and breaks ``_unprefix``'s
    split-on-first-``__``. Non-shared names (e.g. ``composio``,
    ``supabase-clickdns``) already match the spec and pass through.
    """
    s = name
    if s.startswith(SHARED_PREFIX):
        s = "shared_" + s[len(SHARED_PREFIX) :]
    s = re.sub(r"[^A-Za-z0-9_-]", "_", s)
    s = re.sub(r"__+", "_", s).strip("_")
    return (s or "backend")[:64]


def _unwrap_exc(exc: BaseException) -> str:
    """Flatten ExceptionGroups so callers see the root cause.

    The MCP SDK wraps SSE/stdio client failures in an ``ExceptionGroup``
    whose ``str()`` is the opaque "unhandled errors in a TaskGroup (1
    sub-exception)". Walk the group tree and return a readable chain
    ending in the real error (e.g. ``httpx.ConnectError: All connection
    attempts failed``).
    """
    parts: list[str] = []
    cur: BaseException | None = exc
    while cur is not None:
        if isinstance(cur, BaseExceptionGroup):
            # Descend into the first sub-exception; groups here wrap one.
            subs = cur.exceptions
            cur = subs[0] if subs else None
            continue
        parts.append(f"{type(cur).__name__}: {cur}")
        cur = cur.__cause__
    return " | ".join(parts) if parts else str(exc)


def load_config(path: Path) -> tuple[dict[str, Backend], dict[str, Any]]:
    cfg = json.loads(path.read_text())
    servers_cfg = cfg.get("servers", {})
    backends: dict[str, Backend] = {
        name: Backend(name, scfg) for name, scfg in servers_cfg.items()
    }
    shared_cfg = cfg.get("shared_servers", {})
    for name, scfg in shared_cfg.items():
        prefixed = f"{SHARED_PREFIX}{name}"
        backends[prefixed] = Backend(prefixed, scfg)
    return backends, cfg


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------


def _prefixed(tool_name: str, backend_prefix: str) -> str:
    """Join a backend's spec-safe tool_prefix with a backend tool name."""
    return f"{backend_prefix}__{tool_name}"


def _unprefix(prefixed: str) -> tuple[str, str] | None:
    """Split an advertised tool name back into (tool_prefix, original).

    Splits on the FIRST ``__`` so backend tool names that happen to
    contain ``__`` are preserved. The caller maps ``tool_prefix`` back
    to a Backend via ``Backend.tool_prefix`` (the backends dict is keyed
    by the display name, which differs for shared backends).
    """
    backend, sep, original = prefixed.partition("__")
    if not sep or not backend or not original:
        return None
    return backend, original


CONTROL_TOOL_SCHEMAS: dict[str, types.Tool] = {
    "list_servers": types.Tool(
        name="list_servers",
        description=(
            "List all configured MCP backends. Returns a JSON array of "
            "{name, type, port, activated, tool_count} objects."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    "use_server": types.Tool(
        name="use_server",
        description=(
            "Activate a backend MCP server. Connects to it, fetches its "
            "tools, and registers them under the namespace "
            "`<tool_prefix>__<tool_name>` where `<tool_prefix>` is a "
            "spec-safe slug of the backend name (e.g. `composio` -> "
            "`composio__get_version`; `[shared] growthbook` -> "
            "`shared_growthbook__get_projects`). After this call returns, "
            "the LLM MUST call `tools/list` to see the newly registered "
            "tools. Pass `name` = the backend's name from `list_servers`."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Backend name (from list_servers).",
                }
            },
            "required": ["name"],
        },
    ),
    "list_active_servers": types.Tool(
        name="list_active_servers",
        description=(
            "List backends that are currently activated and have tools "
            "registered. Returns a JSON array of "
            "{name, tool_count, tool_names} objects."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    "deactivate_server": types.Tool(
        name="deactivate_server",
        description=(
            "Disconnect from a backend and remove its tools from the "
            "router's tool list. Pass `name` = the backend's name."
        ),
        inputSchema={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Backend name."}},
            "required": ["name"],
        },
    ),
    "reload_servers": types.Tool(
        name="reload_servers",
        description=(
            "Reload the backend registry from mcp_config.json without "
            "restarting the router. New backends become available, removed "
            "backends are deactivated, and changed backends are updated. "
            "After calling this, the LLM MUST call `tools/list` to refresh "
            "its view of available tools."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
}


# ---------------------------------------------------------------------------
# Per-connection Server
# ---------------------------------------------------------------------------


def _build_server(backends: dict[str, Backend]) -> Server:
    """Create a fresh MCP Server with handlers bound to the given backends.

    Each client connection gets its own Server instance so its
    initialization state is isolated. The backends dict is shared so
    activated tools are visible across connections (Claude Code sessions
    may reconnect and expect prior activations to persist).
    """
    server = Server("mcp-router")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        tools = list(CONTROL_TOOL_SCHEMAS.values())
        tools.extend(
            types.Tool(
                name=_prefixed(t.name, backend.tool_prefix),
                description=f"[{backend.name}] {t.description or ''}".strip(),
                inputSchema=t.inputSchema,
            )
            for backend in backends.values()
            for t in backend.tools.values()
        )
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.Content]:
        # Control tools
        if name == "list_servers":
            payload = [
                {
                    "name": b.name,
                    "type": b.cfg.get("type"),
                    "port": b.cfg.get("port"),
                    "url": b.url,
                    "activated": b._session is not None,
                    "tool_count": len(b.tools),
                }
                for b in backends.values()
            ]
            return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]

        if name == "use_server":
            target = arguments.get("name")
            if not isinstance(target, str) or target not in backends:
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(
                            {"ok": False, "error": f"unknown backend: {target!r}"}
                        ),
                    )
                ]
            result = await _activate(target, backends)
            if result.get("ok") and not result.get("already_active"):
                tp = backends[target].tool_prefix
                result["next_step"] = (
                    "Now call `tools/list` so the LLM can see the newly "
                    f"registered tools from `{target}` (advertised as "
                    f"`{tp}__<tool>`, e.g. `{tp}__get_version`)."
                )
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        if name == "list_active_servers":
            payload = [
                {
                    "name": b.name,
                    "tool_count": len(b.tools),
                    "tool_names": list(b.tools.keys()),
                }
                for b in backends.values()
                if b._session is not None
            ]
            return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]

        if name == "deactivate_server":
            target = arguments.get("name")
            if not isinstance(target, str) or target not in backends:
                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps({"ok": False, "error": "unknown backend"}),
                    )
                ]
            result = await _deactivate(target, backends)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        if name == "reload_servers":
            result = await _reload_config(backends)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

        # Dynamic tool: must be prefixed with the backend's spec-safe
        # tool_prefix (e.g. ``shared_growthbook__get_projects``). Map the
        # prefix back to the Backend via tool_prefix — the backends dict
        # is keyed by the display name, which differs for shared ones.
        parts = _unprefix(name)
        if parts is not None:
            prefix, original = parts
            backend = next(
                (b for b in backends.values() if b.tool_prefix == prefix), None
            )
        else:
            backend = None
            original = ""
        if parts is None or backend is None:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "ok": False,
                            "error": (
                                f"tool not found: {name!r}. "
                                "Call `use_server` first, then `tools/list`."
                            ),
                        }
                    ),
                )
            ]
        if backend._session is None:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "ok": False,
                            "error": (
                                f"backend {backend.name!r} is not "
                                "activated. Call `use_server` first."
                            ),
                        }
                    ),
                )
            ]
        return await _forward_call(backend, original, arguments)

    return server


# ---------------------------------------------------------------------------
# Activation / deactivation (shared across connections)
# ---------------------------------------------------------------------------


async def _session_owner(
    backend: Backend,
    ready: asyncio.Future,
    done: asyncio.Future,
    shutdown: asyncio.Event,
) -> None:
    """Own a backend's MCP client session for its entire active lifetime.

    Runs as a standalone ``asyncio`` task in the router's event loop —
    deliberately NOT inside any client connection's ``anyio`` task group.
    The MCP SSE/HTTP client enters its own ``anyio.create_task_group()``
    on ``__aenter__`` (spawning the background reader); because this
    owner task is not a child of a connection's task group, that reader
    is parented to the owner's own cancel scope and survives client
    connections coming and going. The session is created with properly
    nested ``async with`` blocks here so it tears down cleanly on
    deactivation or task cancellation.

    Lifecycle:
      * Signals ``ready`` (result) once the session is initialised and
        tools fetched, or (exception) if setup failed.
      * Stays inside the ``async with`` blocks until ``shutdown`` is set
        (by ``_deactivate``), then exits them — closing the session and
        client streams — and signals ``done``.
      * If the underlying connection drops mid-life, the reader task
        fails, the ``async with`` exits with that exception, and the
        finally block clears ``backend._session`` so later
        ``_forward_call`` callers get a clean "not activated" error
        instead of ``anyio.ClosedResourceError``.
    """
    http_client: httpx.AsyncClient | None = None
    try:
        backend_type = backend.cfg.get("type", "stdio")
        if backend_type == "http":
            headers = backend.cfg.get("headers", {})
            http_client = httpx.AsyncClient(headers=headers) if headers else None
            cm = streamable_http_client(backend.url, http_client=http_client)
        else:
            cm = sse_client(backend.url)
        async with cm as streams:
            if backend_type == "http":
                read_stream, write_stream, _get_session_id = streams
            else:
                read_stream, write_stream = streams
            session = ClientSession(read_stream, write_stream)
            async with session:
                await session.initialize()
                tools_result = await session.list_tools()
                backend.tools = {t.name: t for t in tools_result.tools}
                backend._session = session
                if not ready.done():
                    ready.set_result(None)
                await shutdown.wait()
    except BaseException as exc:
        if not ready.done():
            ready.set_exception(exc)
        elif not isinstance(exc, asyncio.CancelledError):
            log.exception("Session owner for %s failed after ready", backend.name)
    finally:
        backend._session = None
        backend.tools.clear()
        if http_client is not None:
            with contextlib.suppress(Exception):
                await http_client.aclose()
        if not done.done():
            done.set_result(None)


async def _activate(name: str, backends: dict[str, Backend]) -> dict[str, Any]:
    backend = backends[name]
    async with backend._activate_lock:
        if backend._session is not None:
            return {
                "ok": True,
                "already_active": True,
                "name": name,
                "tool_count": len(backend.tools),
            }
        loop = asyncio.get_running_loop()
        ready = loop.create_future()
        done = loop.create_future()
        shutdown = asyncio.Event()
        backend._shutdown = shutdown
        backend._owner_done = done
        backend._owner_task = loop.create_task(
            _session_owner(backend, ready, done, shutdown)
        )
        try:
            await ready
        except BaseException:
            # Setup failed, or _activate itself was cancelled (e.g. the
            # client connection dropped mid-use_server). Either way,
            # abort the owner and wait for it to tear down so no
            # half-built session lingers, then either report the setup
            # error or re-raise the cancellation.
            shutdown.set()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await done
            backend._shutdown = None
            backend._owner_done = None
            backend._owner_task = None
            exc = ready.exception()
            if exc is not None and not isinstance(exc, asyncio.CancelledError):
                log.exception("Failed to activate backend %s", name, exc_info=exc)
                return {"ok": False, "name": name, "error": _unwrap_exc(exc)}
            raise
    return {
        "ok": True,
        "name": name,
        "tool_count": len(backend.tools),
        "tool_names": list(backend.tools.keys()),
    }


async def _reload_config(backends: dict[str, Backend]) -> dict[str, Any]:
    """Reload backend registry from disk, updating the shared backends dict."""
    if _CONFIG_PATH is None:
        return {"ok": False, "error": "router config path is not set"}
    try:
        new_backends, _ = load_config(_CONFIG_PATH)
    except Exception as exc:
        return {"ok": False, "error": f"failed to load config: {exc}"}

    removed: list[str] = []
    for old_name in list(backends.keys()):
        if old_name not in new_backends:
            if backends[old_name]._session is not None:
                await _deactivate(old_name, backends)
            del backends[old_name]
            removed.append(old_name)

    added: list[str] = []
    updated: list[str] = []
    for name, new_backend in new_backends.items():
        if name not in backends:
            backends[name] = new_backend
            added.append(name)
            continue
        old_backend = backends[name]
        if old_backend.cfg != new_backend.cfg:
            if old_backend._session is not None:
                await _deactivate(name, backends)
            backends[name] = new_backend
            updated.append(name)

    log.info(
        "Reloaded config from %s: added=%s updated=%s removed=%s",
        _CONFIG_PATH,
        added,
        updated,
        removed,
    )
    return {
        "ok": True,
        "added": added,
        "updated": updated,
        "removed": removed,
    }


async def _deactivate(name: str, backends: dict[str, Backend]) -> dict[str, Any]:
    backend = backends[name]
    async with backend._activate_lock:
        shutdown = backend._shutdown
        done = backend._owner_done
        if shutdown is None:
            return {"ok": True, "already_inactive": True, "name": name}
        # Signal the owner task to exit its `async with` blocks (closing
        # the session and client streams) and wait for it to finish so
        # the next _activate can spawn a fresh owner cleanly. ``done`` is
        # non-None whenever ``shutdown`` is — they are set together.
        shutdown.set()
        if done is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await done
        backend._shutdown = None
        backend._owner_done = None
        backend._owner_task = None
        backend._session = None
        backend.tools.clear()
    return {"ok": True, "name": name}


async def _forward_call(
    backend: Backend, original_tool: str, arguments: dict[str, Any]
) -> list[types.Content]:
    # Serialise calls per backend — the MCP ClientSession handles one
    # request at a time, so concurrent forwards could interleave responses.
    async with backend._call_lock:
        session = backend._session
        if session is None:
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "ok": False,
                            "error": (
                                f"backend {backend.name!r} session is not "
                                "active (it may have dropped). Re-run "
                                "`use_server` to reconnect."
                            ),
                        }
                    ),
                )
            ]
        try:
            result = await session.call_tool(original_tool, arguments=arguments)
            return list(result.content)
        except Exception as exc:
            log.exception("Backend %s call_tool failed", backend.name)
            return [
                types.TextContent(
                    type="text",
                    text=json.dumps({"ok": False, "error": _unwrap_exc(exc)}),
                )
            ]


# ---------------------------------------------------------------------------
# Unix-socket server
# ---------------------------------------------------------------------------

_conn_counter = 0


def _next_conn_id() -> str:
    global _conn_counter
    _conn_counter += 1
    return f"c{_conn_counter}"


def _short_msg(msg: types.JSONRPCMessage) -> str:
    """Render a JSON-RPC message as a one-line summary for logging."""
    root = msg.root
    if isinstance(root, types.JSONRPCRequest):
        return f"REQ id={root.id} method={root.method}"
    if isinstance(root, types.JSONRPCNotification):
        return f"NOT method={root.method}"
    if isinstance(root, types.JSONRPCResponse):
        return f"RES id={root.id}"
    if isinstance(root, types.JSONRPCError):
        return f"ERR id={root.id} code={root.error.code}"
    return repr(root)[:120]


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    backends: dict[str, Backend],
) -> None:
    """Handle one MCP client connection on a Unix socket.

    Bridges the socket (newline-delimited JSON) to the MCP SDK's
    MemoryObjectStream interface, and runs a fresh Server per connection.
    Every message in both directions is logged with a per-connection ID
    so the full wire traffic is reconstructable from the log file.
    """
    conn_id = _next_conn_id()
    # Create memory streams compatible with the MCP SDK.
    read_stream_writer, read_stream = anyio.create_memory_object_stream(1000)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(1000)
    server = _build_server(backends)

    async def socket_to_mcp() -> None:
        """Read JSON-RPC lines from the socket and feed them to the SDK.

        mcp SDK 1.27+ expects each item on the read stream to be a
        ``SessionMessage`` (a wrapper carrying the ``JSONRPCMessage``
        plus transport metadata). Without this wrap, the SDK's
        ``BaseSession._receive_loop`` raises ``AttributeError`` on the
        first inbound message and the per-connection ``Server.run`` dies.
        """
        buffer = b""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    log.info("[%s] socket EOF", conn_id)
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = types.JSONRPCMessage.model_validate_json(line)
                    except Exception as exc:
                        log.warning(
                            "[%s] C->R INVALID JSON: %r (%s)", conn_id, line, exc
                        )
                        continue
                    log.info("[%s] C->R %s", conn_id, _short_msg(msg))
                    await read_stream_writer.send(SessionMessage(message=msg))
        except anyio.ClosedResourceError:
            pass
        except Exception:
            log.exception("[%s] socket_to_mcp failed", conn_id)
        finally:
            await read_stream_writer.aclose()

    async def mcp_to_socket() -> None:
        """Read SDK messages and write them to the socket as JSON lines.

        The MCP SDK 1.27+ emits ``SessionMessage`` objects on the write
        stream; unwrap ``.message`` to get the raw ``JSONRPCMessage``
        for serialization to the socket.
        """
        try:
            async for session_msg in write_stream_reader:
                summary = _short_msg(session_msg.message)
                log.info("[%s] S->R %s", conn_id, summary)
                data = (
                    session_msg.message.model_dump_json(
                        by_alias=True, exclude_none=True
                    )
                    + "\n"
                )
                writer.write(data.encode("utf-8"))
                await writer.drain()
                log.info("[%s] R->C %s (sent)", conn_id, summary)
        except anyio.ClosedResourceError:
            pass
        except Exception:
            log.exception("[%s] mcp_to_socket failed", conn_id)
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    log.info("[%s] client connected", conn_id)
    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(socket_to_mcp)
            tg.start_soon(mcp_to_socket)
            # ``stateless=True`` tells the MCP SDK's ``ServerSession`` to
            # not require the client to send ``initialize`` +
            # ``notifications/initialized`` before processing requests.
            # fcc-claude (via mcp-proxy-tool) sends ``tools/list`` as the
            # first message with no initialization handshake, so without
            # this flag every request is rejected with "Received request
            # before initialization was complete" (-32602) and fcc-claude
            # shows "tools fetch failed". The router doesn't depend on
            # per-connection init state — it just routes requests — so
            # stateless mode is the correct fit.
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
                stateless=True,
            )
    except Exception:
        log.exception("[%s] Server.run failed", conn_id)
    finally:
        log.info("[%s] client disconnected", conn_id)


async def serve_unix_socket(socket_path: str, backends: dict[str, Backend]) -> None:
    """Listen on a Unix socket and accept MCP client connections forever.

    Implementation note: ``anyio.create_unix_server`` was removed in
    anyio 4.x — its replacement ``create_unix_listener`` has a different
    API (async-iterator based, no callback, no ``serve_forever``). Since
    ``_handle_client`` is already written in terms of asyncio's
    ``StreamReader``/``StreamWriter`` (which is what the MCP SDK's
    ``Server.run`` integrates with via anyio memory streams), the
    minimal fix is to use ``asyncio.start_unix_server`` directly. This
    works transparently inside ``anyio.run()`` because anyio's default
    asyncio backend *is* asyncio.
    """
    # Remove any stale socket file.
    with contextlib.suppress(FileNotFoundError):
        os.unlink(socket_path)
    parent_dir = os.path.dirname(socket_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    os.chmod(parent_dir or ".", 0o700)

    async def on_connect(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await _handle_client(reader, writer, backends)

    server = await asyncio.start_unix_server(on_connect, path=socket_path)
    # Restrict socket permissions.
    with contextlib.suppress(OSError):
        os.chmod(socket_path, 0o600)
    log.info("listening on unix://%s", socket_path)
    async with server:
        await server.serve_forever()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP meta-router (Unix-socket daemon)")
    parser.add_argument(
        "--config",
        default=str(CONFIG_PATH),
        help="Path to mcp_config.json (default: %(default)s)",
    )
    parser.add_argument(
        "--socket",
        required=True,
        help="Unix socket path to listen on (e.g. ~/.mcp-router/sockets/router.sock).",
    )
    parser.add_argument(
        "--log",
        default=os.environ.get("MCP_ROUTER_LOG"),
        help="Optional path to write logs to (in addition to stderr).",
    )
    args = parser.parse_args()

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if args.log:
        handlers.append(logging.FileHandler(args.log))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=handlers,
    )

    global _CONFIG_PATH

    if not Path(args.config).exists():
        log.error("Config not found: %s", args.config)
        return 2

    _CONFIG_PATH = Path(args.config)
    backends, _raw_cfg = load_config(_CONFIG_PATH)
    log.info(
        "Loaded %d backends from %s: %s",
        len(backends),
        args.config,
        ", ".join(b.name for b in backends.values()),
    )

    with contextlib.suppress(KeyboardInterrupt):
        anyio.run(serve_unix_socket, args.socket, backends)
    return 0


if __name__ == "__main__":
    sys.exit(main())
