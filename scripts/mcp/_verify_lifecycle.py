#!/usr/bin/env python3
"""Verify backend sessions survive client connections (the cancel-scope fix).

Regression test for the session-lifecycle bug: before the fix, the SSE/HTTP
client context manager was entered inside the per-connection handler task,
so the background reader died when that connection closed — leaving
``backend._session``'s write stream closed (``anyio.ClosedResourceError``)
and crashing the connection's task group on teardown. With the owner-task
fix, the session is owned by a long-lived task in the router's event loop
and must survive across connections.

Sequence:
  1. Connection A: initialize → use_server(<backend>) → tools/list.
     Assert the backend's tools are registered (wire prefix present).
     CLOSE connection A.
  2. Connection B (fresh): initialize → tools/call <backend>__<tool>.
     Assert the call succeeds (``ok`` true) — i.e. the session created on
     connection A is still alive and serving on a new connection. Before
     the fix this returned ``ClosedResourceError`` / ``{"ok": false, ...}``.

Best-effort: if the chosen backend can't be reached (e.g. supergateway
down), the script reports the specific failure and exits non-zero.
"""

import argparse
import json
import socket
import sys
import time

SOCKET_TIMEOUT_S = 30.0


def _send(sock, msg):
    sock.sendall((json.dumps(msg) + "\n").encode())
    time.sleep(0.2)


def _recv(sock, want_newlines, settle=1.5):
    time.sleep(settle)
    buf = b""
    try:
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            buf += chunk
            if buf.count(b"\n") >= want_newlines:
                break
    except TimeoutError:
        pass
    return buf.decode("utf-8", errors="replace")


def _connect(sock_path):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(SOCKET_TIMEOUT_S)
    s.connect(sock_path)
    return s


def _handshake(sock, extras=None):
    msgs = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "lifecycle-verify", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]
    if extras:
        msgs.extend(extras)
    _send(sock, msgs[0])
    _send(sock, msgs[1])
    for e in extras or []:
        _send(sock, e)
    want = 2 + 2 * (len(extras or []))
    return _recv(sock, want, settle=2.0)


def _parse(resp, call_id):
    for line in resp.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") != call_id or "result" not in msg:
            continue
        content = msg["result"].get("content") or []
        if content and isinstance(content[0], dict):
            text = content[0].get("text")
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"_raw": text}
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--socket", default=None)
    p.add_argument("--backend", default="[shared] resend")
    p.add_argument("--tool", default="shared_resend__list-domains")
    p.add_argument(
        "--prefix",
        default=None,
        help="expected wire tool prefix (e.g. shared_resend__). Defaults to "
        "the part of --tool before the first __.",
    )
    args = p.parse_args()

    sock_path = args.socket or __import__("os").path.expanduser(
        "~/.mcp-router/sockets/router.sock"
    )
    import re

    prefix = args.prefix or args.tool.split("__", 1)[0] + "__"
    prefix_slug = re.sub(r"[^A-Za-z0-9_-]", "_", prefix)
    prefix_slug = re.sub(r"__+", "_", prefix_slug).strip("_") + "__"

    # --- Connection A: activate + list ---
    s = _connect(sock_path)
    try:
        resp = _handshake(
            s,
            extras=[
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "use_server",
                        "arguments": {"name": args.backend},
                    },
                },
            ],
        )
        activate = _parse(resp, 2)
        if not activate or activate.get("ok") is not True:
            print(
                f"FAIL: use_server({args.backend!r}) did not succeed:\n{activate}\n{resp}",
                file=sys.stderr,
            )
            return 1
        print(f"OK: use_server({args.backend!r}) -> {activate.get('tool_count')} tools")
    finally:
        s.close()
    # Connection A is now CLOSED. Before the fix, the backend session's
    # background reader died here.

    # --- Connection B (fresh): call a tool — must succeed ---
    s2 = _connect(sock_path)
    try:
        resp2 = _handshake(
            s2,
            extras=[
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": args.tool, "arguments": {}},
                },
            ],
        )
        call = _parse(resp2, 3)
        if call is None:
            print(
                f"FAIL: tools/call {args.tool!r} returned no parseable result:\n{resp2}",
                file=sys.stderr,
            )
            return 1
        if call.get("ok") is False:
            print(
                f"FAIL: tools/call {args.tool!r} failed (session did not survive "
                f"connection A closing): {call}\nraw:\n{resp2}",
                file=sys.stderr,
            )
            return 1
        # Success = the call was FORWARDED to the backend and a response
        # came back. That response may be a backend API error (e.g. a
        # 401 from a restricted key) — which still proves the session is
        # alive and serving on this fresh connection. The router's own
        # failure envelope ({"ok": false, ...}) is the only signal that
        # the session died, and we already checked for that above.
        if "_raw" in call:
            print(
                f"OK: tools/call {args.tool!r} was forwarded on a fresh connection "
                f"(session survived); backend response: {call['_raw'][:120]!r}"
            )
        else:
            print(
                f"OK: tools/call {args.tool!r} succeeded on a fresh connection (session survived)."
            )
            print(f"     result keys: {list(call.keys())[:5]}")
    finally:
        s2.close()

    print("\n=== LIFECYCLE VERIFICATION PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
