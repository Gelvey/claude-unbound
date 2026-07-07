#!/usr/bin/env python3
"""Bridge Claude Code's stdio MCP transport to the FCC router Unix socket."""

from __future__ import annotations

import argparse
import contextlib
import os
import select
import socket
import sys
import time


def _connect(socket_path: str, timeout_s: float) -> socket.socket:
    deadline = time.monotonic() + timeout_s
    last_error: OSError | None = None

    while time.monotonic() < deadline:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.connect(socket_path)
            client.setblocking(False)
            return client
        except OSError as exc:
            last_error = exc
            client.close()
            time.sleep(0.25)

    detail = f": {last_error}" if last_error is not None else ""
    raise SystemExit(f"mcp_proxy_tool: could not connect to {socket_path}{detail}")


def _relay(client: socket.socket) -> int:
    stdin_fd = sys.stdin.buffer.fileno()
    stdout = sys.stdout.buffer
    stdin_open = True

    while True:
        readers: list[int | socket.socket] = [client]
        if stdin_open:
            readers.append(stdin_fd)

        readable, _, _ = select.select(readers, [], [])
        if client in readable:
            chunk = client.recv(65536)
            if not chunk:
                return 0
            stdout.write(chunk)
            stdout.flush()

        if stdin_open and stdin_fd in readable:
            chunk = os.read(stdin_fd, 65536)
            if not chunk:
                stdin_open = False
                with contextlib.suppress(OSError):
                    client.shutdown(socket.SHUT_WR)
                continue
            client.sendall(chunk)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bridge stdio JSON-RPC to the FCC MCP router Unix socket."
    )
    parser.add_argument(
        "-p",
        "--socket",
        default=os.path.expanduser("~/.mcp-router/sockets/router.sock"),
        help="Path to the FCC MCP router Unix socket.",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=60.0,
        help="Seconds to wait for the router socket to become available.",
    )
    args = parser.parse_args()

    socket_path = os.path.expanduser(args.socket)
    with _connect(socket_path, args.connect_timeout) as client:
        return _relay(client)


if __name__ == "__main__":
    raise SystemExit(main())
