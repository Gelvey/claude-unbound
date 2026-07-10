# Graphify Integration Design — Claude Unbound

**Status:** implemented  
**Target version bump:** `2.19.0` (MINOR — new backward-compatible feature)  
**Date:** 2026-07-10

---

## Executive Summary

Integrate [Graphify](https://github.com/Graphify-Labs/graphify) into Claude Unbound as an **optional, toggleable first-class feature** surfaced in the FCC admin UI as its own **"Graphify"** sidebar tab. The design reuses Unbound's existing **MCP Router** for the actual LLM-to-graph protocol path and introduces a lightweight **project registry** plus **per-session repo detection** so Graphify's naturally per-repo semantics work inside Unbound's currently global, single-tenant architecture.

> **Naming:** the product is **Graphify**; this plan uses "Graphify" throughout.

**High-level flow**

1. User flips `GRAPHIFY_ENABLED=true` in the new Graphify admin tab.
2. Unbound starts a local Graphify **HTTP MCP server** and registers it as an MCP backend in `~/.fcc/mcp_config.json`.
3. The MCP router exposes Graphify tools (`query_graph`, `get_node`, `affected`, etc.) to upstream LLMs.
4. A lightweight **project registry** tracks indexed repos.
5. `fcc-claude` automatically tags each Claude Code session with its repo path; Unbound uses that tag to inject the correct `project_path` into Graphify tool calls.

---

## What Graphify Is (facts from upstream)

- Per-project knowledge-graph builder. Given a folder it produces `graphify-out/graph.json`, `GRAPH_REPORT.md`, HTML/SVG visualizations, etc.
- Ships an **MCP server** (`graphify.serve.serve_http` / `python -m graphify.serve --transport http`) exposing tools such as `query_graph`, `get_node`, `god_nodes`, `shortest_path`, `affected`, `graph_stats`.
- Every MCP tool accepts an optional **`project_path`** argument, so one server process can serve many repos.
- Python dependency is heavy (tree-sitter language packages, optional extras). PyPI package name is **`graphifyy`** (imported as `graphify`).
- Requires Python `>=3.10`; Unbound targets `>=3.14.0`, so it is compatible but should remain **optional**.

---

## The Core Constraint: Per-Project vs. Global

Claude Unbound today has **no per-project/repo concept**. All configuration is global under `~/.fcc/`. Graphify, in contrast, produces one graph per repository root (`<repo>/graphify-out/`).

**Chosen resolution:** add a minimal, explicit **project registry** to Unbound and tag each `fcc-claude` session with its repo path. This keeps the change scoped, backward compatible, and fully automatic once configured.

### Project-handling options considered

| Option | Description | Pros | Cons | Verdict |
|--------|-------------|------|------|---------|
| **A. Auth-token repo suffix** | `fcc-claude` appends `:graphify-repo:<base64path>` to `ANTHROPIC_AUTH_TOKEN`; Unbound parses it per request. | Fully automatic; works with multiple concurrent Claude Code sessions; no routing changes. | Slight env-parsing complexity. | **Chosen** |
| **B. Base-URL path prefix** | `fcc-claude` sets `ANTHROPIC_BASE_URL` to `http://127.0.0.1:<port>/graphify/<repo>`. | Also session-scoped. | Requires dynamic FastAPI routes; changes public URL. | Rejected |
| **C. Active project selector** | Admin UI picks one repo at a time; Graphify server uses it as default. | Simple. | User must switch manually; only one repo at a time. | Rejected as primary |
| **D. Per-project MCP backends** | One Graphify server + port per repo, each a distinct MCP backend. | No argument injection. | High resource/port overhead. | Rejected |
| **E. Global graph only** | Merge all repos into `~/.graphify/global-graph.json`. | Trivial. | Blurs project boundaries. | Rejected |

---

## Key Design Decisions (answered)

### 1. MCP router reload behavior

The router (`scripts/mcp/mcp_router.py`) **loads `mcp_config.json once at startup** (`load_config()` at line 593) and never watches or reloads it. Enabling/disabling Graphify therefore requires the MCP router process to be restarted after the config is updated. The Graphify manager will either:

- restart the router subprocess directly, or
- surface a restart-hint banner in the admin UI telling the user to click **Restart MCP Router**.

Implemented in `scripts/mcp/mcp_router.py` as a JSON-RPC `reload_servers` control tool; `GraphifyManager` uses it automatically with a process-restart fallback for older router versions.

### 2. Dependency mechanism

Graphify is an **optional extra** in `pyproject.toml`:

```toml
[project.optional-dependencies]
graphify = ["graphifyy[mcp]>=0.9.11"]
```

Users can install with `uv sync --extra graphify`. Additionally, the admin UI **Setup** button installs Graphify into an isolated venv under `~/.fcc/graphify/venv/` when it is not present in the main environment. The manager preferentially uses the isolated venv so the feature works even if the user did not sync with the extra.

### 3. Clustering (`[leiden]` extra)

Graphify's `cluster.py` uses **Leiden** when `graspologic` is installed and otherwise falls back to **NetworkX Louvain**. The `[leiden]` extra resolves to `graspologic; python_version < "3.13"`, so it is **not installable on Python 3.14**. Since Unbound requires Python 3.14, there is no point installing the `[leiden]` extra — Graphify will automatically use Louvain.

**Recommendation:** ship only `[mcp]`. If semantic extraction via a particular LLM provider is desired, add the matching backend extra (`[anthropic]`, `[openai]`, etc.) at user request.

### 4. Per-session repo detection with multiple `fcc-claude` instances

A single `fcc-server` handles many Claude Code sessions. To route each session's graph queries to the correct repo:

- `fcc-claude` resolves the repo root (nearest parent containing `.git`, falling back to current working directory).
- It base64-encodes the absolute repo path.
- It appends `:graphify-repo:<base64>` to the `ANTHROPIC_AUTH_TOKEN` env var before launching `claude`.
- Claude Code sends `Authorization: Bearer <token>:graphify-repo:<base64>` on every request.
- Unbound's existing `require_api_key` already strips `:` suffixes before comparing tokens (`api/dependencies.py:118-119`). We extend that logic to also persist the decoded repo path in `request.state.graphify_project_path`.
- When the MCP router forwards a Graphify tool call, Unbound injects `project_path=<decoded-path>` into the arguments before forwarding.

This is stateless, per-request, and works with any number of concurrent sessions.

---

## Recommended Architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                        FCC Admin UI                            │
│  Sidebar tab: "Graphify"                                       │
│  - Enable/Disable toggle                                       │
│  - Status banner (server running/stopped/error)               │
│  - Project registry (add / remove / index repos)              │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP + JSON
                       ▼
┌───────────────────────────────────────────────────────────────┐
│                    api/graphify/manager.py                      │
│  GraphifyManager                                              │
│  - start / stop / restart Graphify HTTP MCP server              │
│  - health-check Graphify `/mcp` endpoint                        │
│  - install / verify `graphifyy` availability                  │
└──────────┬──────────────────────────────────────────────────────┘
           │ manages subprocess   ┌───────────────────────────┐
           ▼                      │  python -m graphify.serve │
  ┌────────────────────┐         │  --transport http           │
  │ ~/.fcc/graphify/   │         │  --host 127.0.0.1           │
  │ projects.json      │         │  --port <dynamic>           │
  │                    │◀────────│                             │
  │ [{path, name, ...}]│         └─────────────────────────────┘
  └────────────────────┘
           │
           │ on enable, writes/updates
           ▼
  ┌────────────────────┐         ┌───────────────────────────┐
  │ ~/.fcc/            │         │    Unbound MCP Router     │
  │ mcp_config.json    │──────▶  │ (existing)                │
  │ servers.graphify   │         │ exposes Graphify tools to │
  └────────────────────┘         │ upstream LLM              │
                                └───────────────────────────┘
```

---

## File-by-File Implementation Plan

### 1. New package `api/graphify/`

Create a dedicated package so the feature is modular and removable.

- **`api/graphify/__init__.py`** — public exports.
- **`api/graphify/config.py`** — Pydantic models:
  ```python
  class GraphifyProject(BaseModel):
      path: str                    # absolute repo root
      name: str                    # friendly name
      graphify_out: str = "graphify-out"
      last_indexed: datetime | None = None
      status: Literal["missing", "indexing", "ready", "stale", "error"] = "missing"
      error_message: str = ""

  class GraphifyProjectRegistry(BaseModel):
      active_project_path: str | None = None
      projects: list[GraphifyProject] = []
  ```
- **`api/graphify/paths.py`** — `projects_json_path() → ~/.fcc/graphify_projects.json`.
- **`api/graphify/projects.py`** — load/save registry, add/remove/update project, list available graphs.
- **`api/graphify/mcp_backend.py`** — build an `McpBackend` dict for Graphify:
  ```python
  def build_graphify_mcp_backend(port: int, api_key: str = "") -> dict[str, Any]:
      return {
          "name": "graphify",
          "type": "http",
          "port": port,
          "url": f"http://127.0.0.1:{port}/mcp",
          "headers": {"Authorization": f"Bearer {api_key}"} if api_key else {},
      }
  ```
- **`api/graphify/manager.py`** — `GraphifyManager` analogous to `providers/freebuff/manager.py`:
  - `__init__(settings: Settings)`
  - `async setup()` — verify/optional install `graphifyy[mcp]`.
  - `async start()` — pick a free port, spawn `python -m graphify.serve --transport http`, write MCP backend entry. **Restart the MCP router** so the new backend is visible.
  - `async stop()` — terminate subprocess, remove backend from `mcp_config.json`, restart router.
  - `async restart()`, `health_check()`, `status()`.
  - `index_project(project: GraphifyProject)` — shell out to `graphify extract <path>` / `graphify update <path>`.

### 2. Settings — `config/settings.py`

Add near `freebuff_enabled` (around line 209):

```python
# ==================== Graphify Config ====================
graphify_enabled: bool = Field(
    default=False,
    validation_alias="GRAPHIFY_ENABLED",
)
graphify_server_port: int = Field(
    default=0,
    validation_alias="GRAPHIFY_SERVER_PORT",
    description="0 selects a free port automatically.",
)
graphify_python_path: str = Field(
    default="",
    validation_alias="GRAPHIFY_PYTHON_PATH",
    description="Optional Python interpreter to run graphify.serve.",
)
graphify_api_key: str = Field(
    default="",
    validation_alias="GRAPHIFY_API_KEY",
    description="API key for Graphify HTTP transport.",
)
graphify_auto_index_on_start: bool = Field(
    default=False,
    validation_alias="GRAPHIFY_AUTO_INDEX_ON_START",
)
```

### 3. Admin config manifest — `api/admin_config.py`

- Add section:
  ```python
  ConfigSectionSpec(
      "graphify",
      "Graphify",
      "Graphify knowledge-graph integration for per-project code understanding.",
  ),
  ```
- Add fields:
  - `GRAPHIFY_ENABLED` → `graphify_enabled`, `boolean`, `restart_required=True`
  - `GRAPHIFY_SERVER_PORT` → `graphify_server_port`, `number`, advanced
  - `GRAPHIFY_PYTHON_PATH` → `graphify_python_path`, advanced
  - `GRAPHIFY_API_KEY` → `graphify_api_key`, `secret`
  - `GRAPHIFY_AUTO_INDEX_ON_START` → `graphify_auto_index_on_start`, `boolean`, advanced

### 4. Environment template — `.env.example`

```ini
# Graphify integration
GRAPHIFY_ENABLED=false
GRAPHIFY_SERVER_PORT=0
GRAPHIFY_PYTHON_PATH=
GRAPHIFY_API_KEY=
GRAPHIFY_AUTO_INDEX_ON_START=false
```

### 5. Admin routes — `api/admin_routes.py`

Add endpoints under `/admin/api/graphify/*`, guarded by `require_loopback_admin(request)`:

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/admin/api/graphify/status` | `{enabled, running, port, version, projects_summary}` |
| POST | `/admin/api/graphify/setup` | Verify/install Graphify package. |
| POST | `/admin/api/graphify/start` | Start the Graphify HTTP server. |
| POST | `/admin/api/graphify/stop` | Stop the server. |
| POST | `/admin/api/graphify/restart` | Restart the server. |
| GET | `/admin/api/graphify/health` | Probe Graphify `/mcp` endpoint. |
| GET | `/admin/api/graphify/projects` | List registered projects. |
| POST | `/admin/api/graphify/projects` | Add or update a project. |
| DELETE | `/admin/api/graphify/projects/{path_b64}` | Remove a project. |
| POST | `/admin/api/graphify/projects/{path_b64}/index` | Run `graphify extract` / `graphify update`. |

Create and attach a `GraphifyManager` instance to `request.app.state.graphify_manager` on first use.

### 6. Per-session repo detection

- **`cli/adapters/claude.py`** — extend `build_launcher_env` to accept an optional `repo_path`. When set, append `:graphify-repo:<base64>` to `ANTHROPIC_AUTH_TOKEN`.
- **`cli/entrypoints.py`** — in `_launch_client_cli`, resolve the repo root from `os.getcwd()` before launching and pass it to the adapter.
- **`api/dependencies.py`** — in `require_api_key`, after stripping the `:model` suffix, also detect `:graphify-repo:<base64>`, decode it, and store it in `request.state.graphify_project_path`.
- **`api/graphify/mcp_proxy.py`** *(new)* — a small middleware/wrapper that intercepts MCP tool calls bound for the `graphify` backend and injects `project_path=request.state.graphify_project_path` when present.

### 7. Admin UI — `api/admin_static/index.html`

Add a new view container after the `view-freebuff` block:

```html
<section id="view-graphify" class="admin-view" data-view="graphify" hidden>
  <div id="graphifySections" class="form-sections" aria-label="Graphify configuration"></div>
</section>
```

### 8. Admin UI — `api/admin_static/admin.js`

- Append to `VIEW_GROUPS`:
  ```js
  {
    id: "graphify",
    label: "Graphify",
    title: "Graphify",
    sections: ["graphify"],
    containerId: "graphifySections",
  },
  ```
- Add `async function loadGraphifyView()` and `renderGraphifyView(status, projects, health)`.
- Render sections:
  1. **Status banner** — running/stopped/error, version, port, router restart hint.
  2. **Action buttons** — Setup, Start, Stop, Restart.
  3. **Project registry** — table with path, status, last indexed, Index/Remove buttons.
  4. **Add Project** — directory picker (text input) + Add button.
- Hook into `apply()` so the view refreshes after config changes.

### 9. Application lifecycle — `api/app.py` and `api/runtime.py`

- In `api/app.py:create_app`, after settings are loaded, if `graphify_enabled` is true, ensure `GraphifyManager` starts and registers the MCP backend.
- In `api/runtime.py` lifespan:
  - On startup: call `GraphifyManager.start()` if enabled.
  - On shutdown: call `GraphifyManager.stop()`.

### 10. MCP Router integration — `api/graphify/mcp_backend.py`

- Read `~/.fcc/mcp_config.json` via `api/mcp_config.py:load_mcp_config`.
- Inject/update a `servers.graphify` entry; remove it on disable.
- **Restart the router** (`scripts/mcp/stop_mcp.sh` then `scripts/mcp/start_mcp.sh`) or display a restart-required banner.

### 11. Packaging and dependencies

- Add to `pyproject.toml`:
  ```toml
  [project.optional-dependencies]
  graphify = ["graphifyy[mcp]>=0.9.11"]
  ```
- `GraphifyManager.setup()` creates `~/.fcc/graphify/venv` and installs `graphifyy[mcp]` if the package is not importable from the main environment.
- Update `pyproject.toml` version to `2.19.0` and run `uv lock`.

### 12. Documentation

- `README.md`: add Graphify to the integration list; document both `uv sync --extra graphify` and the Setup button.
- `ARCHITECTURE.md`: add a "Graphify MCP Integration" checklist under Extension Checklists.
- This plan file remains as historical design record.

---

## Implementation Phases

### Phase 1 — Core Toggle + Status (MVP)

**Goal:** a working Graphify sidebar tab that can enable/disable Graphify and show server status.

- [x] Create `api/graphify/` package skeleton.
- [x] Add `GraphifyManager` with `start`/`stop`/`status` for a single Graphify HTTP server.
- [x] Add settings to `config/settings.py` and `.env.example`.
- [x] Add admin section/fields to `api/admin_config.py`.
- [x] Add admin routes `/admin/api/graphify/status`, `/start`, `/stop`, `/restart`, `/setup`, `/health`.
- [x] Add Graphify sidebar tab in `index.html` and `admin.js`.
- [x] Wire startup/shutdown in `api/runtime.py`.
- [x] Restart the MCP router when the backend config changes.
- [x] Tests: manager lifecycle, route smoke tests, admin UI unit tests.

### Phase 2 — Project Registry + Per-Session Repo Detection

**Goal:** make Graphify per-project/repo and automatic across concurrent Claude Code sessions.

- [x] Add `GraphifyProjectRegistry` and `~/.fcc/graphify_projects.json` persistence.
- [x] Implement project CRUD admin routes.
- [x] Implement `/index` endpoint that runs `graphify extract` / `graphify update` for a project.
- [x] Add project registry UI in `admin.js`.
- [x] Resolve repo root in `fcc-claude` and append `:graphify-repo:<base64>` to `ANTHROPIC_AUTH_TOKEN`.
- [x] Parse the repo suffix in `api/dependencies.py` and store it in `request.state`.
- [x] Inject `project_path` into forwarded Graphify MCP tool calls (via request-pipeline system directive; the shared MCP router has no per-connection context channel).

### Phase 3 — Polish

**Goal:** reliability and UX refinements.

- [x] Add disk-usage guards and `GRAPHIFY_MAX_PROJECT_BYTES`.
- [x] Add watchdog-style auto-reindex when repo files change (optional, enabled via `GRAPHIFY_AUTO_REINDEX`).
- [x] Add live indexing progress in admin UI.
- [x] Add a hot-reload endpoint to `mcp_router.py` so backend changes do not require a full router restart.

---

## Testing Plan

| Test | Location | Notes |
|------|----------|-------|
| Settings parsing | `tests/config/test_settings.py` | Add `GRAPHIFY_*` env vars, assert loaded. |
| Manager lifecycle | `tests/api/graphify/test_manager.py` | Mock subprocess; assert start/stop writes/removes MCP backend. |
| Project registry CRUD | `tests/api/graphify/test_projects.py` | Temp `~/.fcc` dir via fixture; add/remove/index. |
| Admin routes | `tests/api/test_admin_graphify.py` | Loopback-only auth, status payload shape. |
| MCP config mutation | `tests/api/graphify/test_mcp_backend.py` | Verify idempotent add/remove of `servers.graphify`. |
| Repo suffix parsing | `tests/api/test_dependencies.py` | Assert `:graphify-repo:<base64>` is decoded and auth still succeeds. |
| UI | `tests/api/test_admin_static.py` (if exists) or manual | Assert `view-graphify` exists; `VIEW_GROUPS` contains graphify. |
| Live smoke | `smoke/` | Start Unbound with `GRAPHIFY_ENABLED=true` and verify Graphify `/mcp` health via admin route. |

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Graphify is heavy and may conflict with Unbound's deps. | Keep it optional; install in isolated venv by default. |
| MCP router does not reload config. | Restart the router after config changes; document this; future enhancement to add reload signal. |
| Long-running `graphify extract` can block admin HTTP requests. | Run indexing in a background task/thread with polling status endpoint. |
| Graphify can consume a lot of disk for large repos. | Add `GRAPHIFY_MAX_PROJECT_BYTES` / max-repo-size guard; surface disk usage in UI. |
| Security: Graphify server binds to localhost. | Default to `127.0.0.1`, require `GRAPHIFY_API_KEY`, validate paths. |
| Auth-token suffix could collide with existing `:` usage. | Use a unique prefix `graphify-repo:`; strip after the last known prefix. |

---

## Summary of Files Changed

- **New:** `api/graphify/__init__.py`, `api/graphify/config.py`, `api/graphify/paths.py`, `api/graphify/projects.py`, `api/graphify/manager.py`, `api/graphify/mcp_backend.py`, `api/graphify/mcp_proxy.py`
- **Modified:** `config/settings.py`, `api/admin_config.py`, `api/admin_routes.py`, `api/admin_static/index.html`, `api/admin_static/admin.js`, `api/app.py`, `api/runtime.py`, `api/dependencies.py`, `cli/adapters/claude.py`, `cli/entrypoints.py`, `.env.example`, `pyproject.toml`, `uv.lock`, `README.md`, `ARCHITECTURE.md`
- **Tests:** `tests/api/graphify/` (new directory), `tests/config/test_settings.py`, `tests/api/test_dependencies.py`
- **Docs:** this file (`docs/graphify-integration-plan.md`)
