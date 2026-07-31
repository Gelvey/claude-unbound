# Troubleshooting

Common failure modes and how to resolve them.

## Provider 401 / Authentication Errors

**Symptom**: HTTP 503 with a message naming a missing env var (e.g. "NVIDIA_NIM_API_KEY is not set").

The proxy's `require_api_key` dependency checks the `x-api-key` or `Authorization: Bearer` header against `ANTHROPIC_AUTH_TOKEN`. When that token is empty, auth is disabled. The 503 comes from the provider factory: each provider raises `AuthenticationError` with a curated hint when its key is missing or blank.

**Fix**: Open the Admin UI at `/admin`, paste the provider API key into the matching field (e.g. `NVIDIA_NIM_API_KEY`, `OPENROUTER_API_KEY`), click **Validate**, then **Apply**. Restart the server if prompted.

**Symptom**: HTTP 401 "Missing API key" or "Invalid API key".

This is the proxy's own auth check, not the upstream provider. `ANTHROPIC_AUTH_TOKEN` is set but the client is not sending a matching token.

**Fix**: Ensure `fcc-claude` / `fcc-codex` reads the current token from `~/.fcc/.env`. If launching a client manually, set `ANTHROPIC_AUTH_TOKEN` to the same value as the Admin UI auth token.

## MCP Router Socket Errors

**Symptom**: `scripts/mcp/start_mcp.sh` exits with `FATAL: <cmd> not found in PATH`.

The launcher checks for `npx`, `socat`, `jq`, and `uv` before starting. If any are missing, it exits immediately.

**Fix**: Install the missing dependency:
- `npx`: install Node.js (includes `npx`)
- `socat`: `apt install socat` (Debian/Ubuntu) or `brew install socat` (macOS)
- `jq`: `apt install jq` or `brew install jq`
- `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`

**Symptom**: `FATAL: meta-router did not create <socket_path>` or `FATAL: supergateways not healthy`.

The MCP router daemon (`mcp_router.py`) failed to bind its Unix socket, or one or more supergateways did not pass their health check within the configured timeout.

**Fix**: Check the logs at `~/.mcp-router/logs/` (per-backend logs are `<name>.log`, router logs are `router-stdout.log` and the path from `router_log` in the config). Common causes:
- A stdio backend command failed to start (bad path, missing env var).
- A port conflict (another process is using the configured port).
- `npx` cache-install race when two backends share the same package (the script serializes these, but check logs if it still fails).

**Symptom**: `FATAL: <config_path> not found`.

The MCP config file (`~/.fcc/mcp_config.json` by default) does not exist. The launcher creates it from the example on first run via the Admin UI, but if you are starting manually you need to copy it:

```bash
cp scripts/mcp/mcp_config.example.json ~/.fcc/mcp_config.json
```

## Freebuff: "Docker not found"

**Symptom**: Freebuff status shows `error` with the message "Docker not found" or "docker: command not found".

The Freebuff2API manager tries Docker first (`docker run ...`) and falls back to a native binary. If neither Docker nor the binary is available, the setup fails.

**Fix**:
- Install Docker and ensure the user has permission (or the manager will retry with `sudo`).
- Alternatively, let the manager download the Freebuff2API binary automatically (it uses `ensure_binary()` which fetches the prebuilt binary for your platform).

**Symptom**: "No Freebuff auth tokens found."

The credentials file (`~/.config/manicode/credentials.json` by default) is missing or contains no tokens.

**Fix**: Run `npm i -g freebuff && freebuff` to log in and generate credentials, or set `FREEBUFF_CREDENTIALS_PATH` to a custom credentials file.

## Missing Dependencies

The proxy depends on `uv` for Python runtime management. If `uv` is not on `PATH`, the server cannot start.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

The MCP router additionally requires `npx` (Node.js), `socat`, and `jq` (see above).

For voice transcription, install the optional extras:

```bash
# NVIDIA NIM (Riva gRPC)
curl -fsSL "https://github.com/Gelvey/claude-unbound/blob/main/scripts/install.sh?raw=1" | sh -s -- --voice-nim

# Local Whisper (CPU or CUDA)
curl -fsSL "https://github.com/Gelvey/claude-unbound/blob/main/scripts/install.sh?raw=1" | sh -s -- --voice-local
```

## Provider Returns HTTP 400

**Symptom**: A provider returns HTTP 400 for a normal Claude Code request.

Some providers reject non-standard fields or request shapes. The proxy normalizes most of these, but edge cases remain.

**Fix**: Check `LOG_LEVEL=DEBUG` output for the request shape. Common causes:
- `lmstudio` / `llamacpp`: context window too small; increase `--ctx-size` on the model server.
- `groq`: some request fields are unsupported; the adapter strips known-bad shapes but new ones may appear.
- Cloudflare Workers AI: model may not support the requested feature (e.g. tool use); try a different model.
