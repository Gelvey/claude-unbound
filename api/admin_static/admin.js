const state = {
  config: null,
  fields: new Map(),
  localStatus: new Map(),
  modelOptions: [],
  activeView: "providers",
};

const MASKED_SECRET = "********";
const VIEW_GROUPS = [
  {
    id: "providers",
    label: "Providers",
    title: "Providers",
    sections: ["providers", "runtime"],
    containerId: "providersSections",
  },
  {
    id: "model_config",
    label: "Model Config",
    title: "Model Config",
    sections: ["models", "thinking", "permissions", "web_tools"],
    containerId: "modelConfigSections",
  },
  {
    id: "messaging",
    label: "Messaging",
    title: "Messaging",
    sections: ["messaging", "voice"],
    containerId: "messagingSections",
  },
  {
    id: "openrouter_policy",
    label: "OpenRouter",
    title: "OpenRouter Policy",
    sections: ["openrouter_policy"],
    containerId: "openrouterPolicySections",
  },
  {
    id: "cloudflare",
    label: "CloudFlare AI",
    title: "Cloudflare Workers AI",
    sections: ["cloudflare"],
    containerId: "cloudflareSections",
  },
  {
    id: "mcp",
    label: "MCP Router",
    title: "MCP Router",
    sections: [],
    containerId: "mcpSections",
  },
  {
    id: "freebuff",
    label: "Freebuff",
    title: "Freebuff2API",
    sections: ["freebuff"],
    containerId: "freebuffSections",
  },
  {
    id: "graphify",
    label: "Graphify",
    title: "Graphify",
    sections: ["graphify"],
    containerId: "graphifySections",
  },
  {
    id: "diagnostics",
    label: "Diagnostics",
    title: "Diagnostics & Logging",
    sections: ["diagnostics", "smoke"],
    containerId: "diagnosticsSections",
  },
];

const RESTART_MODAL_KEYS = new Set([
  "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS",
  "CODEX_DANGEROUSLY_BYPASS_APPROVALS",
]);

function showRestartModal() {
  const existing = document.querySelector(".restart-modal-overlay");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.className = "restart-modal-overlay";

  const modal = document.createElement("div");
  modal.className = "restart-modal";

  const heading = document.createElement("h3");
  heading.textContent = "Restart Required";

  const body = document.createElement("p");
  body.textContent = "Claude Unbound will need to be restarted to take effect.";

  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.className = "primary-button";
  dismiss.textContent = "OK";
  dismiss.addEventListener("click", () => overlay.remove());

  modal.append(heading, body, dismiss);
  overlay.appendChild(modal);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });
  document.body.appendChild(overlay);
  dismiss.focus();
}

const byId = (id) => document.getElementById(id);

function sourceLabel(source) {
  const labels = {
    default: "default",
    template: "template",
    repo_env: "repo .env",
    managed_env: "",
    explicit_env_file: "FCC_ENV_FILE",
    process: "process env",
    settings_json: "settings.json",
  };
  return Object.prototype.hasOwnProperty.call(labels, source) ? labels[source] : source;
}

function sourceText(field) {
  const parts = [];
  const label = sourceLabel(field.source);
  if (label) {
    parts.push(label);
  }
  if (field.locked) {
    parts.push("locked");
  }
  return parts.join(" ");
}

function providerName(providerId) {
  const names = {
    nvidia_nim: "NVIDIA NIM",
    open_router: "OpenRouter",
    mistral_codestral: "Mistral Codestral",
    deepseek: "DeepSeek",
    lmstudio: "LM Studio",
    llamacpp: "llama.cpp",
    ollama: "Ollama",
    kimi: "Kimi",
    wafer: "Wafer",
    opencode: "OpenCode Zen",
    opencode_go: "OpenCode Go",
    zai: "Z.ai",
    freebuff: "Freebuff",
  };
  if (names[providerId]) return names[providerId];
  return providerId
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function statusClass(status) {
  if (["configured", "reachable", "running"].includes(status)) return "ok";
  if (["missing_key", "missing_url", "unknown"].includes(status)) return "warn";
  if (["offline", "error"].includes(status)) return "error";
  return "neutral";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function load() {
  showMessage("Loading admin config");
  const config = await api("/admin/api/config");
  state.config = config;
  state.fields = new Map(config.fields.map((field) => [field.key, field]));
  await loadModuleTabs();
  renderNav();
  renderProviders(config.provider_status);
  renderSections(config.sections, config.fields);
  byId("configPath").textContent = config.paths.managed;
  await validate(false);
  await refreshLocalStatus();
  updateDirtyState();
  showMessage("");
}

async function loadModuleTabs() {
  try {
    const payload = await api("/admin/api/modules/tabs");
    const tabs = Array.isArray(payload && payload.tabs) ? payload.tabs : [];
    for (const tab of tabs) {
      injectModuleTab(tab);
    }
  } catch (err) {
    // Endpoint may not exist on older builds; non-fatal.
    console.warn("Module tabs endpoint unavailable:", err);
  }
}

function injectModuleTab(tab) {
  if (!tab || !tab.id) return;
  if (VIEW_GROUPS.some((view) => view.id === tab.id)) {
    // Built-in view with same id wins; skip to avoid duplicates.
    return;
  }
  const containerId = `moduleTabSections_${tab.id}`;
  VIEW_GROUPS.push({
    id: tab.id,
    label: tab.label || tab.id,
    title: tab.title || tab.label || tab.id,
    sections: [tab.id],
    containerId,
  });

  const container = document.createElement("section");
  container.className = "admin-view";
  container.dataset.view = tab.id;
  container.id = containerId;
  container.hidden = true;
  container.innerHTML = tab.html || "";

  const viewsRoot = byId("adminViews");
  if (viewsRoot) viewsRoot.appendChild(container);

  if (tab.mount_js) {
    try {
      // eslint-disable-next-line no-new-func
      const mount = new Function("container", tab.mount_js);
      mount(container);
    } catch (err) {
      console.error(`Module tab '${tab.id}' mount_js failed:`, err);
    }
  }
}

function renderNav() {
  const nav = byId("sectionNav");
  nav.innerHTML = "";
  VIEW_GROUPS.forEach((view, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `nav-link${index === 0 ? " active" : ""}`;
    button.dataset.view = view.id;
    button.textContent = view.label;
    if (index === 0) {
      button.setAttribute("aria-current", "page");
    }
    button.addEventListener("click", () => {
      setActiveView(view.id, { scroll: true });
    });
    nav.appendChild(button);
  });
  setActiveView(state.activeView, { scroll: false });
}

function setActiveView(viewId, { scroll = false } = {}) {
  const activeView =
    VIEW_GROUPS.find((view) => view.id === viewId) || VIEW_GROUPS[0];
  state.activeView = activeView.id;
  byId("pageTitle").textContent = activeView.title;

  document.querySelectorAll(".nav-link").forEach((link) => {
    const selected = link.dataset.view === activeView.id;
    link.classList.toggle("active", selected);
    if (selected) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });

  document.querySelectorAll(".admin-view").forEach((view) => {
    const selected = view.dataset.view === activeView.id;
    view.classList.toggle("active", selected);
    view.hidden = !selected;
  });

  if (scroll) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function renderProviders(providerStatus) {
  const grid = byId("providerGrid");
  grid.innerHTML = "";
  providerStatus.forEach((provider) => {
    const card = document.createElement("article");
    card.className = "provider-card";
    card.dataset.provider = provider.provider_id;

    const title = document.createElement("div");
    title.className = "provider-title";
    title.innerHTML = `<strong>${providerName(provider.provider_id)}</strong>`;

    const pill = document.createElement("span");
    pill.className = `status-pill ${statusClass(provider.status)}`;
    pill.textContent = provider.label;
    title.appendChild(pill);

    const meta = document.createElement("div");
    meta.className = "provider-meta";
    meta.textContent =
      provider.kind === "local"
        ? provider.base_url || "No local URL configured"
        : provider.credential_env;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "test-button";
    button.textContent = provider.kind === "local" ? "Test" : "Refresh models";
    button.addEventListener("click", () => testProvider(provider.provider_id, button));

    card.append(title, meta, button);
    grid.appendChild(card);
  });
}

function updateProviderCard(providerId, status, label, metaText) {
  const card = document.querySelector(`[data-provider="${providerId}"]`);
  if (!card) return;
  const pill = card.querySelector(".status-pill");
  pill.className = `status-pill ${statusClass(status)}`;
  pill.textContent = label;
  if (metaText) {
    card.querySelector(".provider-meta").textContent = metaText;
  }
}

function renderSections(sections, fields) {
  VIEW_GROUPS.forEach((view) => {
    byId(view.containerId).innerHTML = "";
  });

  const sectionById = new Map(sections.map((section) => [section.id, section]));
  const bySection = new Map();
  sections.forEach((section) => bySection.set(section.id, []));
  fields.forEach((field) => {
    if (!bySection.has(field.section)) bySection.set(field.section, []);
    bySection.get(field.section).push(field);
  });

  VIEW_GROUPS.forEach((view) => {
    const container = byId(view.containerId);
    view.sections.forEach((sectionId) => {
      const section = sectionById.get(sectionId);
      const sectionFields = bySection.get(sectionId) || [];
      if (!section || sectionFields.length === 0) return;

      const sectionEl = document.createElement("section");
      sectionEl.className = "settings-section";
      sectionEl.id = `section-${section.id}`;

      const heading = document.createElement("div");
      heading.className = "section-heading";
      heading.innerHTML = `<div><h3>${section.label}</h3><p>${section.description}</p></div>`;
      sectionEl.appendChild(heading);

      const grid = document.createElement("div");
      grid.className = "field-grid";
      sectionFields.forEach((field) => {
        grid.appendChild(renderField(field));
      });
      sectionEl.appendChild(grid);

      if (sectionFields.some((field) => field.advanced)) {
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "ghost-button advanced-toggle";
        toggle.textContent = "Show advanced";
        toggle.addEventListener("click", () => {
          const showing = sectionEl.classList.toggle("show-advanced");
          toggle.textContent = showing ? "Hide advanced" : "Show advanced";
        });
        sectionEl.appendChild(toggle);
      }

      container.appendChild(sectionEl);
    });
  });
}

function renderField(field) {
  const wrapper = document.createElement("div");
  wrapper.className = `field${field.advanced ? " advanced-field" : ""}`;
  wrapper.dataset.key = field.key;

  const label = document.createElement("label");
  label.htmlFor = `field-${field.key}`;
  const labelText = document.createElement("span");
  labelText.textContent = field.label;
  label.appendChild(labelText);

  const source = sourceText(field);
  if (source) {
    const sourceEl = document.createElement("span");
    sourceEl.className = "field-source";
    sourceEl.textContent = source;
    label.appendChild(sourceEl);
  }

  const input = inputForField(field);
  input.id = `field-${field.key}`;
  input.dataset.key = field.key;
  input.dataset.original = field.value || "";
  input.dataset.secret = field.secret ? "true" : "false";
  input.dataset.configured = field.configured ? "true" : "false";
  input.disabled = field.locked;
  input.addEventListener("input", updateDirtyState);
  input.addEventListener("change", updateDirtyState);

  if (RESTART_MODAL_KEYS.has(field.key) && field.type === "boolean") {
    input.addEventListener("change", () => {
      if (input.checked) showRestartModal();
    });
  }

  wrapper.append(label, input);
  if (field.description) {
    const description = document.createElement("div");
    description.className = "field-description";
    description.textContent = field.description;
    wrapper.appendChild(description);
  }
  return wrapper;
}

function inputForField(field) {
  if (field.type === "boolean") {
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = String(field.value).toLowerCase() === "true";
    input.dataset.original = input.checked ? "true" : "false";
    return input;
  }

  if (field.type === "tri_boolean") {
    const select = document.createElement("select");
    [
      ["", "Inherit"],
      ["true", "Enabled"],
      ["false", "Disabled"],
    ].forEach(([value, label]) => select.appendChild(option(value, label)));
    select.value = field.value || "";
    return select;
  }

  if (field.type === "select") {
    const select = document.createElement("select");
    field.options.forEach((value) => select.appendChild(option(value, value)));
    select.value = field.value || field.options[0] || "";
    return select;
  }

  if (field.type === "textarea") {
    const textarea = document.createElement("textarea");
    textarea.value = field.value || "";
    return textarea;
  }

  const input = document.createElement("input");
  input.type = field.type === "number" ? "number" : "text";
  if (field.type === "secret") {
    input.type = "password";
    input.placeholder = field.configured
      ? "Configured - enter a new value to replace"
      : "Not configured";
    input.value = "";
    input.autocomplete = "off";
  } else {
    input.value = field.value || "";
  }
  if (field.model_options) {
    input.setAttribute("list", "model-options");
  }
  return input;
}

function option(value, label) {
  const optionEl = document.createElement("option");
  optionEl.value = value;
  optionEl.textContent = label;
  return optionEl;
}

function readFieldValue(input) {
  if (input.type === "checkbox") return input.checked ? "true" : "false";
  if (input.dataset.secret === "true" && input.dataset.configured === "true") {
    return input.value ? input.value : MASKED_SECRET;
  }
  return input.value;
}

function changedValues() {
  const values = {};
  document.querySelectorAll("[data-key]").forEach((input) => {
    if (input.disabled || !input.matches("input, select, textarea")) return;
    const value = readFieldValue(input);
    if (value !== input.dataset.original) {
      values[input.dataset.key] = value;
    }
  });
  return values;
}

function allCurrentValues() {
  const values = {};
  document.querySelectorAll("[data-key]").forEach((input) => {
    if (input.disabled || !input.matches("input, select, textarea")) return;
    values[input.dataset.key] = readFieldValue(input);
  });
  return values;
}

function updateDirtyState() {
  const changed = Object.keys(changedValues()).length;
  const total = Object.keys(allCurrentValues()).length;
  if (changed === 0) {
    byId("dirtyState").textContent = `${total} settings saved`;
    byId("applyButton").disabled = true;
  } else {
    byId("dirtyState").textContent = `${changed} unsaved change${changed === 1 ? "" : "s"} of ${total}`;
    byId("applyButton").disabled = false;
  }
}

async function validate(showResult = true) {
  const result = await api("/admin/api/config/validate", {
    method: "POST",
    body: JSON.stringify({ values: changedValues() }),
  });
  if (showResult) {
    showValidationResult(result);
  }
  return result;
}

function showValidationResult(result) {
  if (result.valid) {
    showMessage("Config shape is valid", "ok");
  } else {
    showMessage(result.errors.join("; "), "error");
  }
}

async function apply() {
  const result = await api("/admin/api/config/apply", {
    method: "POST",
    body: JSON.stringify({ values: allCurrentValues() }),
  });
  if (!result.applied) {
    showValidationResult(result);
    return;
  }
  const restart = result.restart || {};
  if (restart.required && restart.automatic) {
    showMessage("Applied. Restarting server...", "ok");
    byId("applyButton").disabled = true;
    setTimeout(() => {
      window.location.href = restart.admin_url || "/admin";
    }, 1600);
    return;
  }
  const pending = restart.required ? restart.fields || [] : result.pending_fields || [];
  await load();
  // Reload tab-specific views cleared by renderSections
  if (state.activeView === "mcp") await loadMcpView();
  if (state.activeView === "freebuff") await loadFreebuffView();
  if (state.activeView === "graphify") await loadGraphifyView();
  showMessage(
    pending.length
      ? `Applied. Restart fcc-server to use: ${pending.join(", ")}`
      : "Applied",
    "ok",
  );
}

async function refreshLocalStatus() {
  const result = await api("/admin/api/providers/local-status");
  result.providers.forEach((provider) => {
    state.localStatus.set(provider.provider_id, provider);
    const meta = provider.status_code
      ? `${provider.base_url} returned HTTP ${provider.status_code}`
      : provider.base_url;
    updateProviderCard(provider.provider_id, provider.status, provider.label, meta);
  });
}

async function testProvider(providerId, button) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Testing";
  try {
    const result = await api(`/admin/api/providers/${providerId}/test`, {
      method: "POST",
      body: "{}",
    });
    if (result.ok) {
      const prefixed = result.models.map((m) => `${providerId}/${m}`);
      updateProviderCard(
        providerId,
        "reachable",
        `${result.models.length} models`,
        prefixed.slice(0, 3).join(", ") || "No models returned",
      );
      state.modelOptions = Array.from(
        new Set([
          ...state.modelOptions,
          ...result.models.map((model) => `${providerId}/${model}`),
        ]),
      ).sort();
      syncModelDatalist();
    } else {
      console.error(`[${providerId}] Provider test failed:`, result);
      const errorLabel = result.status_code
        ? `HTTP ${result.status_code}`
        : result.error_type;
      const errorMeta = result.request_url
        ? `${result.error_message} (${result.request_url})`
        : result.error_message || result.error_type;
      updateProviderCard(providerId, "offline", errorLabel, errorMeta);
    }
  } catch (error) {
    showMessage(`Provider test failed: ${error.message}`, "error");
    updateProviderCard(providerId, "offline", "Error", error.message);
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function syncModelDatalist() {
  let datalist = byId("model-options");
  if (!datalist) {
    datalist = document.createElement("datalist");
    datalist.id = "model-options";
    document.body.appendChild(datalist);
  }
  datalist.innerHTML = "";
  state.modelOptions.forEach((model) => datalist.appendChild(option(model, model)));
}

function showMessage(message, kind = "") {
  const area = byId("messageArea");
  area.textContent = message;
  area.className = `message-area ${kind}`.trim();
}

byId("validateButton").addEventListener("click", () => validate(true));
byId("applyButton").addEventListener("click", apply);

// ---------------------------------------------------------------------------
// MCP Router admin view
// ---------------------------------------------------------------------------

const mcpState = {
  config: null,
  editingIndex: null, // null = add mode, number = edit mode
};

async function loadMcpView() {
  try {
    const [config, status, sftpResult] = await Promise.all([
      api("/admin/api/mcp/config"),
      api("/admin/api/mcp/status").catch(() => ({ running: false })),
      api("/admin/api/mcp/sftp-config"),
    ]);
    mcpState.config = config;
    config.sftp = sftpResult.sftp || {};
    renderMcpView(config, status);
  } catch (error) {
    byId("mcpSections").innerHTML =
      `<div class="message-area error">Failed to load MCP config: ${error.message}</div>`;
  }
}

function renderMcpView(config, status) {
  const container = byId("mcpSections");
  container.innerHTML = "";

  // Status banner
  const banner = document.createElement("div");
  banner.className = "mcp-status-banner";
  if (status.running) {
    banner.innerHTML =
      `<span class="status-pill ok">Running</span> MCP Router is active (${config.router_socket})`;
  } else {
    banner.innerHTML =
      `<span class="status-pill warn">Not running</span> MCP Router is not running. Start it from the launcher or run <code>bash scripts/mcp/start_mcp.sh</code>`;
  }
  container.appendChild(banner);

  // Refresh button
  const refreshRow = document.createElement("div");
  refreshRow.className = "mcp-action-row";
  const refreshBtn = document.createElement("button");
  refreshBtn.type = "button";
  refreshBtn.className = "secondary-button";
  refreshBtn.textContent = "Refresh Status";
  refreshBtn.addEventListener("click", async () => {
    refreshBtn.disabled = true;
    refreshBtn.textContent = "Refreshing...";
    try {
      const newStatus = await api("/admin/api/mcp/status").catch(() => ({ running: false }));
      renderMcpView(config, newStatus);
    } finally {
      refreshBtn.disabled = false;
      refreshBtn.textContent = "Refresh Status";
    }
  });
  refreshRow.appendChild(refreshBtn);
  container.appendChild(refreshRow);

  // Build live status map from router
  const liveMap = {};
  if (status.backends) {
    status.backends.forEach((b) => {
      liveMap[b.name] = b;
    });
  }

  // Composio quick-setup / status section
  renderComposioSection(config, liveMap, container);

  // Helper to render a backend grid
  function renderBackendGrid(serversObj, label, description, isShared) {
    const section = document.createElement("section");
    section.className = "settings-section";

    const heading = document.createElement("div");
    heading.className = "section-heading";
    heading.innerHTML = `<div><h3>${label}</h3><p>${description}</p></div>`;

    const topAddBtn = document.createElement("button");
    topAddBtn.type = "button";
    topAddBtn.className = "primary-button";
    topAddBtn.textContent = "+ Add Backend";
    topAddBtn.addEventListener("click", () => {
      mcpState.editingIndex = null;
      showMcpEditForm(null, null, isShared);
    });
    heading.appendChild(topAddBtn);
    section.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "field-grid";
    const serverNames = Object.keys(serversObj);

    serverNames.forEach((name) => {
      const srv = serversObj[name];
      const liveKey = isShared ? `[shared] ${name}` : name;
      const live = liveMap[liveKey];
      const card = document.createElement("article");
      card.className = "provider-card";
      card.dataset.mcpBackend = name;
      card.dataset.shared = isShared ? "true" : "false";

      const title = document.createElement("div");
      title.className = "provider-title";
      const displayName = isShared ? `[shared] ${name}` : name;
      title.innerHTML = `<strong>${displayName}</strong>`;

      const pill = document.createElement("span");
      if (live) {
        pill.className = `status-pill ${live.activated ? "ok" : "neutral"}`;
        pill.textContent = live.activated
          ? `${live.tool_count} tool(s)`
          : "configured";
      } else {
        pill.className = "status-pill neutral";
        pill.textContent = srv.type || "stdio";
      }
      title.appendChild(pill);

      const meta = document.createElement("div");
      meta.className = "provider-meta";
      meta.textContent =
        srv.type === "sse" || srv.type === "http"
          ? `${srv.url || ""} (port ${srv.port})`
          : `${srv.command || ""} ${(srv.args || []).join(" ")} (port ${srv.port})`;

      card.append(title, meta);

      const actions = document.createElement("div");
      actions.className = "mcp-backend-actions";

      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "secondary-button";
      editBtn.textContent = "Edit";
      editBtn.addEventListener("click", () => {
        mcpState.editingIndex = serverNames.indexOf(name);
        showMcpEditForm(name, srv, isShared);
      });

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "ghost-button";
      deleteBtn.textContent = "Delete";
      deleteBtn.addEventListener("click", () => {
        const target = isShared
          ? mcpState.config.shared_servers
          : mcpState.config.servers;
        delete target[name];
        saveMcpConfig();
      });

      actions.append(editBtn, deleteBtn);
      card.appendChild(actions);

      if (isShared) {
        const sharedTag = document.createElement("div");
        sharedTag.className = "provider-meta";
        sharedTag.style.cssText =
          "color: var(--accent); font-weight: 600; margin-top: 4px;";
        sharedTag.textContent = "Imported via SFTP";
        card.appendChild(sharedTag);
      }
      grid.appendChild(card);
    });

    section.appendChild(grid);

    const bottomAddBtn = document.createElement("button");
    bottomAddBtn.type = "button";
    bottomAddBtn.className = "primary-button";
    bottomAddBtn.textContent = "+ Add Backend";
    bottomAddBtn.addEventListener("click", () => {
      mcpState.editingIndex = null;
      showMcpEditForm(null, null, isShared);
    });
    section.appendChild(bottomAddBtn);

    container.appendChild(section);
  }

  // Local backends
  renderBackendGrid(
    config.servers || {},
    "Local Backends",
    "Configure MCP server backends managed locally.",
    false,
  );

  // Shared backends (from SFTP or manually added)
  renderBackendGrid(
    config.shared_servers || {},
    "Shared Backends",
    "Backends shared across teammates (imported via SFTP or added manually).",
    true,
  );

  // Router settings
  const routerSection = document.createElement("section");
  routerSection.className = "settings-section";
  const routerHeading = document.createElement("div");
  routerHeading.className = "section-heading";
  routerHeading.innerHTML = `<div><h3>Router Settings</h3><p>Socket path, log path, and health timeout.</p></div>`;
  routerSection.appendChild(routerHeading);

  const routerGrid = document.createElement("div");
  routerGrid.className = "field-grid";
  [
    { key: "router_socket", label: "Socket Path", value: config.router_socket },
    { key: "router_log", label: "Log Path", value: config.router_log },
    { key: "router_pidfile", label: "PID File", value: config.router_pidfile },
    { key: "health_timeout_s", label: "Health Timeout (s)", value: String(config.health_timeout_s) },
  ].forEach((field) => {
    const wrapper = document.createElement("div");
    wrapper.className = "field";
    const label = document.createElement("label");
    label.textContent = field.label;
    const input = document.createElement("input");
    input.type = "text";
    input.value = field.value || "";
    input.dataset.mcpRouterKey = field.key;
    input.addEventListener("change", () => {
      if (field.key === "health_timeout_s") {
        mcpState.config[field.key] = parseInt(input.value, 10) || 30;
      } else {
        mcpState.config[field.key] = input.value;
      }
    });
    wrapper.append(label, input);
    routerGrid.appendChild(wrapper);
  });
  routerSection.appendChild(routerGrid);
  container.appendChild(routerSection);

  // SFTP shared config section
  renderSftpSection(config, container);
}

function renderSftpSection(config, container) {
  const sftp = config.sftp || {};
  const section = document.createElement("section");
  section.className = "settings-section";
  section.id = "sftp-section";

  const heading = document.createElement("div");
  heading.className = "section-heading";
  heading.innerHTML = `<div><h3>Shared Config (SFTP)</h3><p>Fetch and import a shared MCP config from a remote server via SFTP.</p></div>`;
  section.appendChild(heading);

  // Status banner
  const banner = document.createElement("div");
  banner.className = "mcp-status-banner";
  if (sftp.enabled && sftp.host) {
    banner.innerHTML = `<span class="status-pill ok">Enabled</span> SFTP configured: ${sftp.username || ""}@${sftp.host || ""}:${sftp.port || 22} &rarr; ${sftp.remote_file_path || ""}`;
  } else {
    banner.innerHTML = `<span class="status-pill neutral">Not configured</span> Set up SFTP credentials to share MCP config across teammates.`;
  }
  section.appendChild(banner);

  // SFTP config fields
  const grid = document.createElement("div");
  grid.className = "field-grid";

  const SFTP_FIELD_MAP = {
    host: "FCC_SFTP_HOST",
    port: "FCC_SFTP_PORT",
    username: "FCC_SFTP_USERNAME",
    auth_method: "FCC_SFTP_AUTH_METHOD",
    password: "FCC_SFTP_PASSWORD",
    private_key: "FCC_SFTP_PRIVATE_KEY",
    remote_file_path: "FCC_SFTP_REMOTE_FILE_PATH",
    enabled: "FCC_SFTP_ENABLED",
  };

  function sftpField(key, label, type, value, placeholder) {
    const wrapper = document.createElement("div");
    wrapper.className = "field";
    wrapper.dataset.sftpField = key;
    const lbl = document.createElement("label");
    lbl.textContent = label;
    const input = document.createElement(type === "checkbox" ? "input" : (type === "select" ? "select" : (type === "textarea" ? "textarea" : "input")));
    let actualValue = value;
    if (type === "checkbox") {
      input.type = "checkbox";
      input.checked = !!value;
      actualValue = value ? "true" : "false";
    } else if (type === "select") {
      // handled below
    } else if (type === "textarea") {
      input.value = value || "";
      input.placeholder = placeholder || "";
      actualValue = value || "";
    } else {
      input.type = type;
      input.value = value || "";
      input.placeholder = placeholder || "";
      actualValue = value || "";
    }
    // Wire into global Apply button via data-key
    const envKey = SFTP_FIELD_MAP[key];
    if (envKey) {
      input.dataset.key = envKey;
      input.dataset.original = String(actualValue);
      input.addEventListener("input", updateDirtyState);
      input.addEventListener("change", updateDirtyState);
    }
    wrapper.append(lbl, input);
    grid.appendChild(wrapper);
    return input;
  }

  const hostInput = sftpField("host", "Host", "text", sftp.host, "e.g. sftp.example.com");
  const portInput = sftpField("port", "Port", "number", sftp.port || 22, "22");
  const userInput = sftpField("username", "Username", "text", sftp.username, "e.g. teamuser");

  // Auth method select
  const authWrapper = document.createElement("div");
  authWrapper.className = "field";
  authWrapper.dataset.sftpField = "auth_method";
  const authLabel = document.createElement("label");
  authLabel.textContent = "Auth Method";
  const authSelect = document.createElement("select");
  ["password", "key"].forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m === "password" ? "Password" : "Private Key";
    if ((sftp.auth_method || "password") === m) opt.selected = true;
    authSelect.appendChild(opt);
  });
  authSelect.dataset.key = SFTP_FIELD_MAP.auth_method;
  authSelect.dataset.original = sftp.auth_method || "password";
  authSelect.addEventListener("input", updateDirtyState);
  authSelect.addEventListener("change", updateDirtyState);
  authWrapper.append(authLabel, authSelect);
  grid.appendChild(authWrapper);

  const passwordInput = sftpField("password", "Password", "password", "", "Enter password");
  if (sftp.password === MASKED_SECRET) {
    passwordInput.value = "";
    passwordInput.placeholder = "Configured — enter a new value to replace";
    passwordInput.dataset.secret = "true";
    passwordInput.dataset.configured = "true";
    passwordInput.dataset.original = MASKED_SECRET;
  }
  passwordInput.dataset.masked = sftp.password === MASKED_SECRET ? "true" : "false";

  const keyInput = sftpField("private_key", "Private Key", "textarea", "", "Paste private key");
  if (sftp.private_key === MASKED_SECRET) {
    keyInput.value = "";
    keyInput.placeholder = "Configured — enter a new value to replace";
    keyInput.dataset.secret = "true";
    keyInput.dataset.configured = "true";
    keyInput.dataset.original = MASKED_SECRET;
  }
  keyInput.dataset.masked = sftp.private_key === MASKED_SECRET ? "true" : "false";

  const filePathInput = sftpField("remote_file_path", "Remote File Path", "text", sftp.remote_file_path, "/home/team/shared-mcp/mcp_config.json");

  // Toggle visibility based on auth method
  function updateSftpFieldVisibility() {
    const method = authSelect.value;
    passwordInput.closest(".field").style.display = method === "password" ? "" : "none";
    keyInput.closest(".field").style.display = method === "key" ? "" : "none";
  }
  authSelect.addEventListener("change", updateSftpFieldVisibility);
  updateSftpFieldVisibility();

  // Enabled checkbox
  const enabledWrapper = document.createElement("div");
  enabledWrapper.className = "field";
  enabledWrapper.dataset.sftpField = "enabled";
  const enabledLabel = document.createElement("label");
  enabledLabel.textContent = "Enabled";
  const enabledCheckbox = document.createElement("input");
  enabledCheckbox.type = "checkbox";
  enabledCheckbox.checked = !!sftp.enabled;
  enabledCheckbox.dataset.key = SFTP_FIELD_MAP.enabled;
  enabledCheckbox.dataset.original = sftp.enabled ? "true" : "false";
  enabledCheckbox.addEventListener("change", updateDirtyState);
  enabledWrapper.append(enabledLabel, enabledCheckbox);
  grid.appendChild(enabledWrapper);

  section.appendChild(grid);

  // Action buttons
  const actions = document.createElement("div");
  actions.className = "mcp-action-row";
  actions.style.cssText = "margin-top: 16px; flex-wrap: wrap;";

  const testBtn = document.createElement("button");
  testBtn.type = "button";
  testBtn.className = "secondary-button";
  testBtn.textContent = "Test Connection";
  testBtn.addEventListener("click", () => sftpTestConnection(section, grid));

  const fetchBtn = document.createElement("button");
  fetchBtn.type = "button";
  fetchBtn.className = "primary-button";
  fetchBtn.textContent = "Fetch Remote Config";
  fetchBtn.addEventListener("click", () => sftpDoFetch(section, grid));

  actions.append(testBtn, fetchBtn);
  section.appendChild(actions);

  container.appendChild(section);
}

function readSftpFields(grid) {
  const result = {};
  grid.querySelectorAll("[data-sftp-field]").forEach((wrapper) => {
    const key = wrapper.dataset.sftpField;
    if (key === "enabled") {
      result[key] = wrapper.querySelector("input[type='checkbox']").checked;
    } else {
      const input = wrapper.querySelector("input, select, textarea");
      if (input) {
        if (input.type === "number") {
          result[key] = parseInt(input.value, 10) || 22;
        } else {
          result[key] = input.value;
        }
      }
    }
  });
  // Carry forward masked state for password/key
  const pwInput = grid.querySelector("[data-sftp-field='password'] input");
  if (pwInput && pwInput.dataset.masked === "true" && !result.password) {
    result.password = MASKED_SECRET;
  }
  const keyInput = grid.querySelector("[data-sftp-field='private_key'] textarea");
  if (keyInput && keyInput.dataset.masked === "true" && !result.private_key) {
    result.private_key = MASKED_SECRET;
  }
  return result;
}

async function sftpTestConnection(section, grid) {
  clearSftpMessages(section);
  const values = readSftpFields(grid);
  try {
    const validateResult = await api("/admin/api/mcp/sftp-config/validate", {
      method: "POST",
      body: JSON.stringify(values),
    });
    if (!validateResult.valid) {
      showSftpMessage(section, validateResult.errors.join("; "), "error");
      return;
    }
    // Save first, then try fetch
    await api("/admin/api/mcp/sftp-config/apply", {
      method: "POST",
      body: JSON.stringify(values),
    });
    const fetchResult = await api("/admin/api/mcp/sftp-fetch", { method: "POST" });
    if (fetchResult.ok) {
      const count = Object.keys(fetchResult.config.servers || {}).length;
      showSftpMessage(section, `Connection successful. Found ${count} remote backend(s).`, "ok");
      showSftpPreview(section, fetchResult.config);
    } else {
      showSftpMessage(section, fetchResult.error || "Connection failed", "error");
      removeSftpPreview(section);
    }
  } catch (error) {
    showSftpMessage(section, `Failed: ${error.message}`, "error");
    removeSftpPreview(section);
  }
}

async function sftpDoFetch(section, grid) {
  clearSftpMessages(section);
  removeSftpPreview(section);
  try {
    // Save config first so changes to fields are used
    const values = readSftpFields(grid);
    await api("/admin/api/mcp/sftp-config/apply", {
      method: "POST",
      body: JSON.stringify(values),
    });
    const result = await api("/admin/api/mcp/sftp-fetch", { method: "POST" });
    if (result.ok) {
      const count = Object.keys(result.config.servers || {}).length;
      showSftpMessage(section, `Fetched ${count} remote backend(s).`, "ok");
      showSftpPreview(section, result.config);
    } else {
      showSftpMessage(section, result.error || "Fetch failed", "error");
    }
  } catch (error) {
    showSftpMessage(section, `Fetch failed: ${error.message}`, "error");
  }
}

async function sftpImport(section, mode) {
  clearSftpMessages(section);
  try {
    const result = await api("/admin/api/mcp/sftp-import", {
      method: "POST",
      body: JSON.stringify({ mode }),
    });
    if (result.ok) {
      showSftpMessage(section, `Imported ${result.imported_count || 0} backend(s) (${mode}). Reloading...`, "ok");
      removeSftpPreview(section);
      setTimeout(() => loadMcpView(), 300);
    } else {
      showSftpMessage(section, result.error || "Import failed", "error");
    }
  } catch (error) {
    showSftpMessage(section, `Import failed: ${error.message}`, "error");
  }
}

function showSftpPreview(section, remoteConfig) {
  removeSftpPreview(section);
  const servers = remoteConfig.servers || {};
  const names = Object.keys(servers);
  if (!names.length) return;

  const preview = document.createElement("div");
  preview.className = "sftp-preview";
  preview.id = "sftp-preview";

  const header = document.createElement("div");
  header.className = "sftp-preview-header";
  header.innerHTML = `<strong>Remote Backends (${names.length})</strong><span>Review before importing</span>`;

  const list = document.createElement("div");
  list.className = "sftp-preview-list";
  names.forEach((name) => {
    const srv = servers[name];
    const item = document.createElement("div");
    item.className = "provider-card";
    item.innerHTML =
      `<div class="provider-title"><strong>${name}</strong><span class="status-pill neutral">${srv.type || "stdio"}</span></div>` +
      `<div class="provider-meta">${srv.type === "sse" || srv.type === "http" ? (srv.url || "") : (srv.command || "")} (port ${srv.port || "?"})</div>`;
    list.appendChild(item);
  });

  const actionRow = document.createElement("div");
  actionRow.className = "sftp-preview-actions";
  const mergeBtn = document.createElement("button");
  mergeBtn.type = "button";
  mergeBtn.className = "primary-button";
  mergeBtn.textContent = "Merge into Local";
  mergeBtn.addEventListener("click", () => sftpImport(section, "merge"));

  const replaceBtn = document.createElement("button");
  replaceBtn.type = "button";
  replaceBtn.className = "secondary-button";
  replaceBtn.textContent = "Replace All Local";
  replaceBtn.addEventListener("click", () => sftpImport(section, "replace"));

  actionRow.append(mergeBtn, replaceBtn);
  preview.append(header, list, actionRow);
  section.appendChild(preview);
  preview.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function removeSftpPreview(section) {
  const existing = section.querySelector("#sftp-preview");
  if (existing) existing.remove();
}

function clearSftpMessages(section) {
  const existing = section.querySelector(".sftp-message");
  if (existing) existing.remove();
}

function showSftpMessage(section, message, kind) {
  clearSftpMessages(section);
  const msg = document.createElement("div");
  msg.className = `message-area sftp-message ${kind}`;
  msg.style.cssText = "margin-top: 12px;";
  msg.textContent = message;
  section.appendChild(msg);
}

function renderComposioSection(config, liveMap, container) {
  const composio = config.servers && config.servers.composio;
  const composioLive = liveMap.composio;
  const composioShared = _findComposioShared(config);
  const section = document.createElement("section");
  section.className = "settings-section composio-section";

  if (!composio) {
    // --- Quick-setup card ---
    const heading = document.createElement("div");
    heading.className = "section-heading";
    heading.innerHTML = `<div><h3>Composio</h3><p>Connect to Composio's MCP marketplace to access hundreds of tools (GitHub, Slack, Stripe, Notion, and more). <a href="https://composio.dev" target="_blank" rel="noopener">Get an API key</a></p></div>`;
    section.appendChild(heading);

    if (composioShared) {
      const note = document.createElement("div");
      note.className = "composio-shared-note";
      note.textContent = `Also configured as a shared server: "${composioShared}". Manage it from the Shared Servers section.`;
      section.appendChild(note);
    }

    const card = document.createElement("div");
    card.className = "composio-setup-card";

    const keyField = document.createElement("div");
    keyField.className = "field";
    const keyLabel = document.createElement("label");
    keyLabel.textContent = "Composio API Key";
    const keyInput = document.createElement("input");
    keyInput.type = "password";
    keyInput.placeholder = "Enter your Composio API key";
    keyField.append(keyLabel, keyInput);
    card.appendChild(keyField);

    const actions = document.createElement("div");
    actions.className = "mcp-action-row";

    const connectBtn = document.createElement("button");
    connectBtn.type = "button";
    connectBtn.className = "primary-button";
    connectBtn.textContent = "Connect Composio";
    connectBtn.addEventListener("click", async () => {
      const apiKey = keyInput.value.trim();
      if (!apiKey) {
        showMessage("Please enter your Composio API key", "error");
        keyInput.focus();
        return;
      }
      connectBtn.disabled = true;
      connectBtn.textContent = "Connecting...";
      try {
        const result = await api("/admin/api/mcp/composio/setup", {
          method: "POST",
          body: JSON.stringify({ api_key: apiKey }),
        });
        if (result.applied) {
          showMessage("Composio connected successfully", "ok");
          keyInput.value = "";
          await loadMcpView();
        } else {
          showMessage(result.errors ? result.errors.join("; ") : "Setup failed", "error");
        }
      } catch (error) {
        showMessage(`Setup failed: ${error.message}`, "error");
      } finally {
        connectBtn.disabled = false;
        connectBtn.textContent = "Connect Composio";
      }
    });

    actions.appendChild(connectBtn);
    card.appendChild(actions);
    section.appendChild(card);
  } else {
    // --- Status card ---
    const heading = document.createElement("div");
    heading.className = "section-heading";
    heading.innerHTML = `<div><h3>Composio</h3><p>Connected to Composio MCP marketplace. <a href="https://composio.dev" target="_blank" rel="noopener">composio.dev</a></p></div>`;
    section.appendChild(heading);

    if (composioShared) {
      const note = document.createElement("div");
      note.className = "composio-shared-note";
      note.textContent = `Also configured as a shared server: "${composioShared}". Manage it from the Shared Servers section.`;
      section.appendChild(note);
    }

    const card = document.createElement("div");
    card.className = "composio-status-card";

    // Status row
    const statusRow = document.createElement("div");
    statusRow.className = "composio-status-row";
    const pill = document.createElement("span");
    if (composioLive && composioLive.activated) {
      pill.className = "status-pill ok";
      pill.textContent = `${composioLive.tool_count} tool(s) available`;
    } else if (composioLive) {
      pill.className = "status-pill neutral";
      pill.textContent = "Configured (not activated)";
    } else {
      pill.className = "status-pill neutral";
      pill.textContent = "Configured";
    }
    statusRow.appendChild(pill);

    // Tool names if available
    if (composioLive && composioLive.tool_names && composioLive.tool_names.length > 0) {
      const toolsList = document.createElement("div");
      toolsList.className = "composio-tools-list";
      toolsList.textContent = composioLive.tool_names.join(", ");
      statusRow.appendChild(toolsList);
    }
    card.appendChild(statusRow);

    // API key update field
    const keyField = document.createElement("div");
    keyField.className = "field";
    const keyLabel = document.createElement("label");
    keyLabel.textContent = "Update API Key";
    const keyInput = document.createElement("input");
    keyInput.type = "password";
    keyInput.placeholder = "Enter new key to replace";
    keyField.append(keyLabel, keyInput);
    card.appendChild(keyField);

    const hint = document.createElement("div");
    hint.className = "field-hint";
    hint.textContent =
      "Leave the field empty and click Test Connection to verify the currently saved key.";
    card.appendChild(hint);

    // Action buttons
    const actions = document.createElement("div");
    actions.className = "mcp-action-row";

    const testBtn = document.createElement("button");
    testBtn.type = "button";
    testBtn.className = "secondary-button";
    testBtn.textContent = "Test Connection";
    testBtn.addEventListener("click", async () => {
      testBtn.disabled = true;
      testBtn.textContent = "Testing...";
      try {
        const apiKey = keyInput.value.trim();
        const body = apiKey ? { api_key: apiKey } : {};
        const result = await api("/admin/api/mcp/composio/test", {
          method: "POST",
          body: JSON.stringify(body),
        });
        if (result.ok) {
          const suffix = apiKey ? "new key" : "current key";
          showMessage(
            `Composio OK (${suffix}): ${result.tool_count} tools available`,
            "ok",
          );
        } else {
          showMessage(`Composio test failed: ${result.error}`, "error");
        }
      } catch (error) {
        showMessage(`Test failed: ${error.message}`, "error");
      } finally {
        testBtn.disabled = false;
        testBtn.textContent = "Test Connection";
      }
    });

    const updateBtn = document.createElement("button");
    updateBtn.type = "button";
    updateBtn.className = "primary-button";
    updateBtn.textContent = "Update Key";
    updateBtn.addEventListener("click", async () => {
      const apiKey = keyInput.value.trim();
      if (!apiKey) {
        showMessage("Enter a new API key to update", "error");
        keyInput.focus();
        return;
      }
      updateBtn.disabled = true;
      updateBtn.textContent = "Updating...";
      try {
        const result = await api("/admin/api/mcp/composio/setup", {
          method: "POST",
          body: JSON.stringify({ api_key: apiKey, port: composio.port }),
        });
        if (result.applied) {
          showMessage("Composio API key updated", "ok");
          keyInput.value = "";
          await loadMcpView();
        } else {
          showMessage(result.errors ? result.errors.join("; ") : "Update failed", "error");
        }
      } catch (error) {
        showMessage(`Update failed: ${error.message}`, "error");
      } finally {
        updateBtn.disabled = false;
        updateBtn.textContent = "Update Key";
      }
    });

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "ghost-button composio-remove-btn";
    removeBtn.textContent = "Remove";
    _wireComposioRemove(removeBtn, () => {
      delete config.servers.composio;
      return saveMcpConfig();
    });

    actions.append(testBtn, updateBtn, removeBtn);
    card.appendChild(actions);
    section.appendChild(card);
  }

  container.appendChild(section);
}

// Detect a Composio entry in shared_servers by name or by URL convention.
function _findComposioShared(config) {
  const shared = (config && config.shared_servers) || {};
  for (const [name, srv] of Object.entries(shared)) {
    if (name === "composio-shared") return name;
    if (srv && typeof srv.url === "string" && srv.url.includes("composio.dev")) {
      return name;
    }
  }
  return null;
}

// Two-step confirm: first click arms the button, second click commits.
function _wireComposioRemove(button, onConfirm) {
  let armed = false;
  let resetTimer = null;
  let originalLabel = button.textContent;

  function reset() {
    armed = false;
    button.textContent = originalLabel;
    button.classList.remove("armed");
    if (resetTimer) {
      clearTimeout(resetTimer);
      resetTimer = null;
    }
  }

  button.addEventListener("click", async () => {
    if (!armed) {
      armed = true;
      button.textContent = "Confirm Remove?";
      button.classList.add("armed");
      // Auto-disarm after 4s so an abandoned click doesn't linger.
      resetTimer = setTimeout(reset, 4000);
      return;
    }
    button.disabled = true;
    button.textContent = "Removing...";
    try {
      await onConfirm();
    } finally {
      button.disabled = false;
      reset();
    }
  });
}

function showMcpEditForm(name, srv, isShared) {
  const existingForm = byId("mcpEditForm");
  if (existingForm) existingForm.remove();

  const form = document.createElement("div");
  form.id = "mcpEditForm";
  form.className = "mcp-edit-form";

  const isEdit = name !== null;
  const title = document.createElement("h3");
  title.textContent = isEdit ? `Edit Backend: ${name}` : "Add Backend";
  form.appendChild(title);

  // Name
  const nameField = createFormInput("Name", isEdit ? name : "", "text", !isEdit);
  nameField.querySelector("input").dataset.fieldName = "name";

  // Type
  const typeSelect = document.createElement("select");
  typeSelect.dataset.fieldName = "type";
  ["stdio", "sse", "http"].forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    if (srv && srv.type === t) opt.selected = true;
    typeSelect.appendChild(opt);
  });
  const typeField = createFormSelect("Type", typeSelect);

  // Port
  const portField = createFormInput("Port", srv ? String(srv.port) : "7101", "number");

  // Command (stdio)
  const commandField = createFormInput("Command", srv ? srv.command || "" : "", "text");
  commandField.dataset.showFor = "stdio";

  // Args (stdio)
  const argsField = createFormInput("Args (comma-separated)", (srv && srv.args) ? srv.args.join(", ") : "", "text");
  argsField.dataset.showFor = "stdio";

  // Env (stdio) - key=value rows
  const envField = document.createElement("div");
  envField.className = "field";
  envField.dataset.showFor = "stdio";
  const envLabel = document.createElement("label");
  envLabel.textContent = "Environment Variables";
  envField.appendChild(envLabel);
  const envRows = document.createElement("div");
  envRows.className = "mcp-env-rows";
  const existingEnv = (srv && srv.env) ? srv.env : {};
  Object.entries(existingEnv).forEach(([key, value]) => {
    addEnvRow(envRows, key, value);
  });
  const addEnvBtn = document.createElement("button");
  addEnvBtn.type = "button";
  addEnvBtn.className = "ghost-button";
  addEnvBtn.textContent = "+ Add env var";
  addEnvBtn.addEventListener("click", () => addEnvRow(envRows, "", ""));
  envField.appendChild(envRows);
  envField.appendChild(addEnvBtn);

  // URL (sse / http)
  const urlField = createFormInput("URL", srv ? srv.url || "" : "", "text");
  urlField.dataset.showFor = "sse,http";
  const urlHint = document.createElement("div");
  urlHint.className = "field-hint";
  urlHint.textContent = "For Composio: https://connect.composio.dev/mcp";
  urlHint.dataset.showFor = "http";

  // Headers (http) - key=value rows
  const headersField = document.createElement("div");
  headersField.className = "field";
  headersField.dataset.showFor = "http";
  const headersLabel = document.createElement("label");
  headersLabel.textContent = "HTTP Headers";
  const headersHint = document.createElement("div");
  headersHint.className = "field-hint";
  headersHint.textContent = "Authentication headers (e.g., x-consumer-api-key for Composio)";
  headersField.append(headersLabel, headersHint);
  const headersRows = document.createElement("div");
  headersRows.className = "mcp-env-rows";
  const existingHeaders = (srv && srv.headers) ? srv.headers : {};
  Object.entries(existingHeaders).forEach(([key, value]) => {
    addEnvRow(headersRows, key, value);
  });
  const addHeaderBtn = document.createElement("button");
  addHeaderBtn.type = "button";
  addHeaderBtn.className = "ghost-button";
  addHeaderBtn.textContent = "+ Add header";
  addHeaderBtn.addEventListener("click", () => addEnvRow(headersRows, "", ""));
  headersField.appendChild(headersRows);
  headersField.appendChild(addHeaderBtn);

  form.append(nameField, typeField, portField, commandField, argsField, envField, urlField, urlHint, headersField);

  // Toggle visibility based on type
  function updateFieldVisibility() {
    const selectedType = typeSelect.value;
    [commandField, argsField, envField].forEach((f) => {
      f.style.display = selectedType === "stdio" ? "" : "none";
    });
    urlField.style.display =
      selectedType === "sse" || selectedType === "http" ? "" : "none";
    urlHint.style.display = selectedType === "http" ? "" : "none";
    headersField.style.display = selectedType === "http" ? "" : "none";
  }
  typeSelect.addEventListener("change", updateFieldVisibility);
  updateFieldVisibility();

  // Buttons
  const actions = document.createElement("div");
  actions.className = "mcp-form-actions";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "primary-button";
  saveBtn.textContent = isEdit ? "Save Changes" : "Add Backend";
  saveBtn.addEventListener("click", () => {
    const newName = nameField.querySelector("input").value.trim();
    const newType = typeSelect.value;
    const newPort = parseInt(portField.querySelector("input").value, 10) || 7101;
    const newCommand = commandField.querySelector("input").value.trim();
    const newArgs = argsField.querySelector("input").value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const newUrl = urlField.querySelector("input").value.trim();

    // Read env rows
    const newEnv = {};
    envRows.querySelectorAll(".mcp-env-row").forEach((row) => {
      const k = row.querySelector("input[placeholder='KEY']").value.trim();
      const v = row.querySelector("input[placeholder='VALUE']").value;
      if (k) newEnv[k] = v;
    });

    // Read header rows
    const newHeaders = {};
    headersRows.querySelectorAll(".mcp-env-row").forEach((row) => {
      const k = row.querySelector("input[placeholder='KEY']").value.trim();
      const v = row.querySelector("input[placeholder='VALUE']").value;
      if (k) newHeaders[k] = v;
    });

    // Build server entry
    const entry = { type: newType, port: newPort };
    if (newType === "stdio") {
      entry.command = newCommand;
      entry.args = newArgs;
      entry.env = newEnv;
    } else if (newType === "http") {
      entry.url = newUrl;
      entry.headers = newHeaders;
    } else {
      entry.url = newUrl;
    }

    // Save to the correct config section
    const target = isShared
      ? mcpState.config.shared_servers
      : mcpState.config.servers;
    if (!target) {
      // Ensure shared_servers exists
      mcpState.config.shared_servers = {};
    }
    const saveTarget = isShared
      ? mcpState.config.shared_servers
      : mcpState.config.servers;
    // If renaming, remove old entry
    if (isEdit && name !== newName) {
      delete saveTarget[name];
    }
    saveTarget[newName] = entry;
    form.remove();
    saveMcpConfig();
  });

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "secondary-button";
  cancelBtn.textContent = "Cancel";
  cancelBtn.addEventListener("click", () => form.remove());

  actions.append(saveBtn, cancelBtn);
  form.appendChild(actions);

  byId("mcpSections").appendChild(form);
  form.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function createFormInput(labelText, value, type, disabled) {
  const wrapper = document.createElement("div");
  wrapper.className = "field";
  const label = document.createElement("label");
  label.textContent = labelText;
  const input = document.createElement("input");
  input.type = type || "text";
  input.value = value || "";
  if (disabled) input.disabled = true;
  wrapper.append(label, input);
  return wrapper;
}

function createFormSelect(labelText, select) {
  const wrapper = document.createElement("div");
  wrapper.className = "field";
  const label = document.createElement("label");
  label.textContent = labelText;
  wrapper.append(label, select);
  return wrapper;
}

function addEnvRow(container, key, value) {
  const row = document.createElement("div");
  row.className = "mcp-env-row";
  const keyInput = document.createElement("input");
  keyInput.type = "text";
  keyInput.placeholder = "KEY";
  keyInput.value = key;
  const valueInput = document.createElement("input");
  valueInput.type = value === MASKED_SECRET ? "password" : "text";
  valueInput.placeholder = "VALUE";
  valueInput.value = value === MASKED_SECRET ? "" : value;
  if (value === MASKED_SECRET) {
    valueInput.dataset.masked = "true";
    valueInput.title = "Masked — leave empty to keep unchanged";
  }
  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "ghost-button";
  removeBtn.textContent = "×";
  removeBtn.addEventListener("click", () => row.remove());
  row.append(keyInput, valueInput, removeBtn);
  container.appendChild(row);
}

async function saveMcpConfig() {
  try {
    const result = await api("/admin/api/mcp/config/apply", {
      method: "POST",
      body: JSON.stringify(mcpState.config),
    });
    if (result.applied) {
      showMessage(
        `${result.restart_hint || "Saved"}`,
        "ok",
      );
      await loadMcpView();
    } else {
      showMessage(result.errors.join("; ") || "Validation failed", "error");
    }
  } catch (error) {
    showMessage(`Save failed: ${error.message}`, "error");
  }
}

// Load MCP view when its tab is activated
function onMcpViewActivated() {
  if (state.activeView === "mcp") {
    loadMcpView();
  }
}

// ---------------------------------------------------------------------------
// Freebuff2API admin view
// ---------------------------------------------------------------------------

const freebuffState = {
  status: null,
  health: null,
};

async function loadFreebuffView() {
  const container = byId("freebuffSections");

  // Show loading indicator (preserve existing config sections)
  let loadingIndicator = container.querySelector("#freebuff-loading");
  if (!loadingIndicator) {
    loadingIndicator = document.createElement("div");
    loadingIndicator.id = "freebuff-loading";
    loadingIndicator.className = "mcp-status-banner";
    loadingIndicator.innerHTML = '<span class="status-pill neutral">⏳ Loading</span> Checking Freebuff2API status...';
    loadingIndicator.style.cssText = "opacity: 0.7; font-size: 0.9em;";
    container.appendChild(loadingIndicator);
  }

  try {
    const [status, health] = await Promise.all([
      api("/admin/api/freebuff/status"),
      api("/admin/api/freebuff/health").catch(() => ({ status: "unreachable" })),
    ]);
    freebuffState.status = status;
    freebuffState.health = health;
    renderFreebuffView(status, health);
  } catch (error) {
    // Remove loading indicator on error
    if (loadingIndicator) {
      loadingIndicator.remove();
    }
    // Show error message after config sections
    const errorDiv = document.createElement("div");
    errorDiv.className = "message-area error";
    errorDiv.textContent = `Failed to load Freebuff status: ${error.message}`;
    container.appendChild(errorDiv);
  }
}

function renderFreebuffView(status, health) {
  const container = byId("freebuffSections");

  // Remove loading indicator
  const loadingIndicator = container.querySelector("#freebuff-loading");
  if (loadingIndicator) {
    loadingIndicator.remove();
  }

  // Remove existing status sections if they exist (but keep config sections)
  const existingStatus = container.querySelector("#freebuff-status-section");
  if (existingStatus) {
    existingStatus.remove();
  }

  // Create a wrapper for all dynamic status content
  const statusSection = document.createElement("div");
  statusSection.id = "freebuff-status-section";

  // -- Session hygiene / suspension-risk warning (always shown) --
  const suspensionWarning = document.createElement("div");
  suspensionWarning.className = "mcp-status-banner warning-banner";
  suspensionWarning.innerHTML =
    '<span class="status-pill warn">⚠ Suspension Risk</span> Freebuff free-tier models can get your account suspended in long sessions. Start a new session periodically; don\'t reuse one conversation for hundreds of turns.';
  statusSection.appendChild(suspensionWarning);

  // -- Sudo warning banner --
  if (status.requires_sudo) {
    const sudoWarning = document.createElement("div");
    sudoWarning.className = "mcp-status-banner warning-banner";
    sudoWarning.innerHTML =
      '<span class="status-pill warn">⚠ Sudo Required</span> Docker requires elevated permissions. You may need to add your user to the docker group: <code>sudo usermod -aG docker $USER</code> and log out/in.';
    statusSection.appendChild(sudoWarning);
  }

  // -- Status banner --
  const banner = document.createElement("div");
  banner.className = "mcp-status-banner";
  const runState = status.running ? "ok" : "neutral";
  const runLabel = status.running ? "Active" : "Stopped";
  const methodInfo = status.method ? ` (${status.method})` : "";
  const portInfo = status.port ? ` on port ${status.port}` : "";
  const healthInfo = status.health && status.health !== "unknown" ? ` - ${status.health}` : "";
  banner.innerHTML =
    `<span class="status-pill ${runState}">${runLabel}</span> Freebuff2API${methodInfo}${portInfo}${healthInfo}`;
  statusSection.appendChild(banner);

  // -- Action buttons --
  const actions = document.createElement("div");
  actions.className = "mcp-action-row";

  const setupBtn = document.createElement("button");
  setupBtn.type = "button";
  setupBtn.className = "secondary-button";
  setupBtn.textContent = "Setup";
  setupBtn.title = "Ensure binary/image, read credentials, generate config";
  setupBtn.addEventListener("click", async () => {
    setupBtn.disabled = true;
    setupBtn.textContent = "Setting up...";
    try {
      const result = await api("/admin/api/freebuff/setup", { method: "POST" });
      if (result.status === "ready") {
        showMessage(
          `Freebuff ready — ${result.token_count} token(s), port ${result.port}`,
          "ok",
        );
      } else {
        showMessage(result.error || "Setup failed", "error");
      }
      await loadFreebuffView();
    } catch (error) {
      showMessage(`Setup failed: ${error.message}`, "error");
    } finally {
      setupBtn.disabled = false;
      setupBtn.textContent = "Setup";
    }
  });

  const startBtn = document.createElement("button");
  startBtn.type = "button";
  startBtn.className = "primary-button";
  startBtn.textContent = "Start";
  startBtn.disabled = status.running;
  startBtn.addEventListener("click", async () => {
    startBtn.disabled = true;
    startBtn.textContent = "Starting...";
    try {
      const result = await api("/admin/api/freebuff/start", { method: "POST" });
      if (result.success) {
        showMessage("Freebuff started successfully", "ok");
      } else {
        const errorMsg = result.error || result.status?.container?.error || "Start failed - check Docker logs";
        showMessage(errorMsg, "error");
      }
      await loadFreebuffView();
    } catch (error) {
      showMessage(`Start failed: ${error.message}`, "error");
    } finally {
      startBtn.disabled = false;
      startBtn.textContent = "Start";
    }
  });

  const stopBtn = document.createElement("button");
  stopBtn.type = "button";
  stopBtn.className = "secondary-button";
  stopBtn.textContent = "Stop";
  stopBtn.disabled = !status.running;
  stopBtn.addEventListener("click", async () => {
    stopBtn.disabled = true;
    stopBtn.textContent = "Stopping...";
    try {
      await api("/admin/api/freebuff/stop", { method: "POST" });
      showMessage("Freebuff stopped", "ok");
      await loadFreebuffView();
    } catch (error) {
      showMessage(`Stop failed: ${error.message}`, "error");
    } finally {
      stopBtn.disabled = false;
      stopBtn.textContent = "Stop";
    }
  });

  const restartBtn = document.createElement("button");
  restartBtn.type = "button";
  restartBtn.className = "secondary-button";
  restartBtn.textContent = "Restart";
  restartBtn.addEventListener("click", async () => {
    restartBtn.disabled = true;
    restartBtn.textContent = "Restarting...";
    try {
      const result = await api("/admin/api/freebuff/restart", { method: "POST" });
      if (result.success) {
        showMessage("Freebuff restarted", "ok");
      } else {
        showMessage("Restart failed", "error");
      }
      await loadFreebuffView();
    } catch (error) {
      showMessage(`Restart failed: ${error.message}`, "error");
    } finally {
      restartBtn.disabled = false;
      restartBtn.textContent = "Restart";
    }
  });

  const refreshBtn = document.createElement("button");
  refreshBtn.type = "button";
  refreshBtn.className = "secondary-button";
  refreshBtn.textContent = "Refresh";
  refreshBtn.addEventListener("click", async () => {
    refreshBtn.disabled = true;
    refreshBtn.textContent = "Refreshing...";
    try {
      await loadFreebuffView();
    } finally {
      refreshBtn.disabled = false;
      refreshBtn.textContent = "Refresh";
    }
  });

  actions.append(setupBtn, startBtn, stopBtn, restartBtn, refreshBtn);
  statusSection.appendChild(actions);

  // -- Credentials section --
  const credSection = document.createElement("section");
  credSection.className = "settings-section";
  const credHeading = document.createElement("div");
  credHeading.className = "section-heading";
  credHeading.innerHTML = "<div><h3>Credentials</h3><p>Auth tokens read from the Freebuff CLI credentials file.</p></div>";
  credSection.appendChild(credHeading);

  const credGrid = document.createElement("div");
  credGrid.className = "field-grid";
  const creds = status.credentials || {};
  const credCard = document.createElement("article");
  credCard.className = "provider-card";
  const credFound = creds.found;
  const credPill = `<span class="status-pill ${credFound ? "ok" : "warn"}">${credFound ? `${creds.token_count} token(s)` : "Not found"}</span>`;
  const credProfiles = creds.profiles && creds.profiles.length
    ? `<div style="margin-top:4px;font-size:0.85em;opacity:0.8">Profiles: ${creds.profiles.join(", ")}</div>`
    : "";
  const credPath = creds.path
    ? `<div style="margin-top:2px;font-size:0.8em;opacity:0.6">${creds.path}</div>`
    : "";
  credCard.innerHTML =
    `<div class="provider-title"><strong>Freebuff CLI Tokens</strong>${credPill}</div>${credProfiles}${credPath}`;
  credGrid.appendChild(credCard);
  credSection.appendChild(credGrid);
  statusSection.appendChild(credSection);

  // -- Binary / deployment section --
  const binSection = document.createElement("section");
  binSection.className = "settings-section";
  const binHeading = document.createElement("div");
  binHeading.className = "section-heading";
  binHeading.innerHTML = "<div><h3>Deployment</h3><p>Binary or Docker image availability.</p></div>";
  binSection.appendChild(binHeading);

  const binGrid = document.createElement("div");
  binGrid.className = "field-grid";
  const bin = status.binary || {};

  const dockerCard = document.createElement("article");
  dockerCard.className = "provider-card";
  const dockerAvail = bin.docker_available;
  dockerCard.innerHTML =
    `<div class="provider-title"><strong>Docker</strong>` +
    `<span class="status-pill ${dockerAvail ? "ok" : "neutral"}">${dockerAvail ? "Available" : "Not installed"}</span></div>` +
    `<div style="margin-top:4px;font-size:0.85em;opacity:0.8">${bin.method === "docker" ? "Active deployment method" : "Primary method (pulls from ghcr.io/gelvey/freebuff2api:latest)"}</div>`;
  binGrid.appendChild(dockerCard);

  const goCard = document.createElement("article");
  goCard.className = "provider-card";
  const goAvail = bin.go_available;
  goCard.innerHTML =
    `<div class="provider-title"><strong>Go Build</strong>` +
    `<span class="status-pill ${goAvail ? "ok" : "neutral"}">${goAvail ? "Available" : "Not installed"}</span></div>` +
    `<div style="margin-top:4px;font-size:0.85em;opacity:0.8">${bin.method === "source" ? "Active deployment method" : "Fallback: build from source"}</div>`;
  binGrid.appendChild(goCard);

  if (bin.binary_exists) {
    const binCard = document.createElement("article");
    binCard.className = "provider-card";
    binCard.innerHTML =
      `<div class="provider-title"><strong>Built Binary</strong>` +
      `<span class="status-pill ok">Exists</span></div>` +
      `<div style="margin-top:4px;font-size:0.85em;opacity:0.8">${bin.binary_path || ""}</div>`;
    binGrid.appendChild(binCard);
  }

  if (bin.version) {
    const verCard = document.createElement("article");
    verCard.className = "provider-card";
    verCard.innerHTML =
      `<div class="provider-title"><strong>Version</strong>` +
      `<span class="status-pill neutral">${bin.version}</span></div>`;
    binGrid.appendChild(verCard);
  }

  binSection.appendChild(binGrid);
  statusSection.appendChild(binSection);

  // -- Health check section --
  const healthSection = document.createElement("section");
  healthSection.className = "settings-section";
  const healthHeading = document.createElement("div");
  healthHeading.className = "section-heading";
  healthHeading.innerHTML = "<div><h3>Health & Status</h3><p>Live health probe of the Freebuff2API instance.</p></div>";
  healthSection.appendChild(healthHeading);

  const healthGrid = document.createElement("div");
  healthGrid.className = "field-grid";

  // Docker container status card
  const containerStatus = status.container || {};
  const containerCard = document.createElement("article");
  containerCard.className = "provider-card";
  const containerRunning = containerStatus.running;
  const containerPillClass = containerRunning ? "ok"
    : containerStatus.status === "exited" ? "warn"
    : "neutral";
  const containerLabel = containerRunning ? "Active"
    : containerStatus.status === "exited" ? "Stopped"
    : containerStatus.status === "not_found" ? "Not Found"
    : "Unknown";
  let containerMeta = "";
  if (containerStatus.container_id) {
    containerMeta += `<div style="margin-top:4px;font-size:0.85em;opacity:0.8">Container ID: ${containerStatus.container_id.substring(0, 12)}</div>`;
  }
  if (containerStatus.error) {
    containerMeta += `<div style="margin-top:2px;font-size:0.8em;color:#e74c3c">${containerStatus.error}</div>`;
  }
  containerCard.innerHTML =
    `<div class="provider-title"><strong>Docker Container</strong>` +
    `<span class="status-pill ${containerPillClass}">${containerLabel}</span></div>${containerMeta}`;
  healthGrid.appendChild(containerCard);

  // Health endpoint card
  const healthCard = document.createElement("article");
  healthCard.className = "provider-card";
  const healthStatus = health.status || status.health || "unknown";
  const healthPillClass = healthStatus === "healthy" ? "ok"
    : healthStatus === "not_configured" ? "neutral"
    : "error";
  let healthMeta = "";
  if (health.uptime_sec != null) {
    const mins = Math.floor(health.uptime_sec / 60);
    const secs = Math.floor(health.uptime_sec % 60);
    healthMeta += `<div style="margin-top:4px;font-size:0.85em;opacity:0.8">Uptime: ${mins}m ${secs}s</div>`;
  }
  if (health.error) {
    healthMeta += `<div style="margin-top:2px;font-size:0.8em;opacity:0.7">${health.error}</div>`;
  }
  healthCard.innerHTML =
    `<div class="provider-title"><strong>Health Endpoint</strong>` +
    `<span class="status-pill ${healthPillClass}">${healthStatus}</span></div>${healthMeta}`;
  healthGrid.appendChild(healthCard);

  // Token state from health check
  if (health.token_state && health.token_state.length) {
    health.token_state.forEach((token) => {
      const tCard = document.createElement("article");
      tCard.className = "provider-card";
      const sessionStatus = token.session_status || token.status || token.state || "unknown";
      const tPillClass = sessionStatus === "active" || sessionStatus === "ok" || sessionStatus === "healthy" ? "ok"
        : sessionStatus === "rate_limited" || sessionStatus === "cooldown" || sessionStatus === "draining" ? "warn"
        : "neutral";
      const runCount = token.runs ? token.runs.length : 0;
      const inflightCount = token.runs
        ? token.runs.reduce((sum, r) => sum + (r.inflight || 0), 0)
        : 0;
      let tMeta = `<div style="margin-top:4px;font-size:0.85em;opacity:0.8">${runCount} active run(s), ${inflightCount} in-flight</div>`;
      if (token.session_expires_at && token.session_expires_at !== "0001-01-01T00:00:00Z") {
        const expires = new Date(token.session_expires_at);
        const minsLeft = Math.max(0, Math.round((expires - Date.now()) / 60000));
        tMeta += `<div style="margin-top:2px;font-size:0.8em;opacity:0.7">Session expires in ~${minsLeft}m</div>`;
      }
      tCard.innerHTML =
        `<div class="provider-title"><strong>${token.name || "Token"}</strong>` +
        `<span class="status-pill ${tPillClass}">${sessionStatus}</span></div>${tMeta}`;
      healthGrid.appendChild(tCard);
    });
  }

  healthSection.appendChild(healthGrid);
  statusSection.appendChild(healthSection);

  // -- Models section --
  const modelsSection = document.createElement("section");
  modelsSection.className = "settings-section";
  const modelsHeading = document.createElement("div");
  modelsHeading.className = "section-heading";
  modelsHeading.innerHTML =
    `<div><h3>Models</h3><p>${status.model_count || 0} model(s) available through the Freebuff2API proxy.</p></div>`;
  modelsSection.appendChild(modelsHeading);

  const modelsRefreshRow = document.createElement("div");
  modelsRefreshRow.className = "mcp-action-row";
  const modelsRefreshBtn = document.createElement("button");
  modelsRefreshBtn.type = "button";
  modelsRefreshBtn.className = "secondary-button";
  modelsRefreshBtn.textContent = "Discover Models";
  modelsRefreshBtn.addEventListener("click", async () => {
    modelsRefreshBtn.disabled = true;
    modelsRefreshBtn.textContent = "Discovering...";
    try {
      const result = await api("/admin/api/freebuff/models");
      freebuffState.status.models = result.models;
      freebuffState.status.model_count = result.models.length;
      renderFreebuffView(freebuffState.status, freebuffState.health);
    } catch (error) {
      showMessage(`Model discovery failed: ${error.message}`, "error");
    } finally {
      modelsRefreshBtn.disabled = false;
      modelsRefreshBtn.textContent = "Discover Models";
    }
  });
  modelsRefreshRow.appendChild(modelsRefreshBtn);
  modelsSection.appendChild(modelsRefreshRow);

  const models = status.models || [];
  if (models.length) {
    const modelGrid = document.createElement("div");
    modelGrid.className = "field-grid";
    models.forEach((model) => {
      const mCard = document.createElement("article");
      mCard.className = "provider-card";
      const mId = model.id || model.model || "unknown";
      mCard.innerHTML =
        `<div class="provider-title"><strong>${mId}</strong>` +
        `<span class="status-pill ok">available</span></div>` +
        `<div style="margin-top:2px;font-size:0.8em;opacity:0.7">Proxied via Freebuff2API</div>`;
      modelGrid.appendChild(mCard);
    });
    modelsSection.appendChild(modelGrid);
  }

  statusSection.appendChild(modelsSection);

  // Append the entire status section to the container (AFTER config fields)
  container.appendChild(statusSection);
}

// Load Freebuff view when its tab is activated
function onFreebuffViewActivated() {
  if (state.activeView === "freebuff") {
    loadFreebuffView();
  }
}

// ---------------------------------------------------------------------------
// Graphify admin view
// ---------------------------------------------------------------------------

const graphifyState = {
  status: null,
  projects: [],
  health: null,
  refreshTimer: null,
};

function stopGraphifyAutoRefresh() {
  if (graphifyState.refreshTimer) {
    clearInterval(graphifyState.refreshTimer);
    graphifyState.refreshTimer = null;
  }
}

function startGraphifyAutoRefreshIfBusy() {
  const busy = graphifyState.projects.some(
    (p) => p.status === "indexing" || p.status === "queued",
  );
  if (!busy) {
    stopGraphifyAutoRefresh();
    return;
  }
  if (graphifyState.refreshTimer) return;
  graphifyState.refreshTimer = setInterval(async () => {
    if (state.activeView !== "graphify") {
      stopGraphifyAutoRefresh();
      return;
    }
    try {
      const [statusResult, projectsResult] = await Promise.all([
        api("/admin/api/graphify/status"),
        api("/admin/api/graphify/projects"),
      ]);
      graphifyState.status = statusResult;
      graphifyState.projects = projectsResult.projects || [];
      renderGraphifyView(statusResult, graphifyState.projects, graphifyState.health);
    } catch {
      // Swallow transient polling errors; the next tick retries.
    }
  }, 10000);
}

async function loadGraphifyView() {
  const container = byId("graphifySections");
  let loadingIndicator = container.querySelector("#graphify-loading");
  if (!loadingIndicator) {
    loadingIndicator = document.createElement("div");
    loadingIndicator.id = "graphify-loading";
    loadingIndicator.className = "mcp-status-banner";
    loadingIndicator.innerHTML = '<span class="status-pill neutral">⏳ Loading</span> Checking Graphify status...';
    loadingIndicator.style.cssText = "opacity: 0.7; font-size: 0.9em;";
    container.appendChild(loadingIndicator);
  }

  try {
    const [statusResult, healthResult, projectsResult] = await Promise.all([
      api("/admin/api/graphify/status"),
      api("/admin/api/graphify/health").catch(() => ({ status: "unreachable" })),
      api("/admin/api/graphify/projects"),
    ]);
    graphifyState.status = statusResult;
    graphifyState.health = healthResult;
    graphifyState.projects = projectsResult.projects || [];
    renderGraphifyView(statusResult, graphifyState.projects, healthResult);
    startGraphifyAutoRefreshIfBusy();
  } catch (error) {
    if (loadingIndicator) {
      loadingIndicator.remove();
    }
    const errorDiv = document.createElement("div");
    errorDiv.className = "message-area error";
    errorDiv.textContent = `Failed to load Graphify status: ${error.message}`;
    container.appendChild(errorDiv);
  }
}

function graphifyStatusPillClass(status) {
  if (status === "ready") return "ok";
  if (status === "indexing") return "warn";
  if (status === "queued") return "warn";
  if (status === "error") return "error";
  if (status === "stale") return "warn";
  return "neutral";
}

function graphifyStatusLabel(status) {
  if (status === "queued") return "queued";
  return status || "missing";
}

function graphifyHealthPill(health, running) {
  if (!running) return { cls: "neutral", label: "Stopped" };
  const s = (health && health.status) || "unreachable";
  if (s === "healthy") return { cls: "ok", label: "Healthy" };
  if (s === "unhealthy") return { cls: "error", label: "Unhealthy" };
  if (s === "not_configured") return { cls: "neutral", label: "Not configured" };
  return { cls: "warn", label: "Unreachable" };
}

function fmtNum(n) {
  return (n || 0).toLocaleString();
}

async function loadGraphSummary(pathB64, target) {
  try {
    const summary = await api(`/admin/api/graphify/projects/${pathB64}/graph`);
    if (!summary || summary.present === false) {
      if (summary && summary.reason === "not_indexed") {
        target.textContent = "Graph not built yet";
      }
      return;
    }
    const commit = summary.built_at_commit
      ? ` · commit ${String(summary.built_at_commit).slice(0, 7)}`
      : "";
    target.innerHTML =
      `📊 ${fmtNum(summary.node_count)} nodes · ${fmtNum(summary.link_count)} links · `
      + `${fmtNum(summary.hyperedge_count)} hyperedges${commit}`;
    target.dataset.loaded = "1";
  } catch {
    // Summary endpoint unavailable; leave the slot empty.
  }
}

function renderGraphifyView(status, projects, health) {
  const container = byId("graphifySections");
  const loadingIndicator = container.querySelector("#graphify-loading");
  if (loadingIndicator) {
    loadingIndicator.remove();
  }

  const existingStatus = container.querySelector("#graphify-status-section");
  if (existingStatus) {
    existingStatus.remove();
  }

  const statusSection = document.createElement("div");
  statusSection.id = "graphify-status-section";

  const banner = document.createElement("div");
  banner.className = "mcp-status-banner";
  const runState = status.running ? "ok" : status.last_error ? "error" : "neutral";
  const runLabel = status.running ? "Running" : status.last_error ? "Error" : "Stopped";
  const hp = graphifyHealthPill(health, status.running);
  const portInfo = status.port ? ` · port ${status.port}` : "";
  const pythonInfo = status.python ? ` · ${status.python}` : "";
  const mcpPill = status.mcp_registered
    ? ' <span class="status-pill ok">MCP registered</span>'
    : ' <span class="status-pill neutral">MCP unregistered</span>';
  const projectCount = status.projects_count ?? projects.length;
  const countInfo = ` · ${projectCount} project${projectCount === 1 ? "" : "s"}`;
  let backendInfo = "";
  if (status.llm_backend) {
    backendInfo = ` · backend ${status.llm_backend}`;
    if (status.llm_model) backendInfo += ` (${status.llm_model})`;
  } else if (status.code_only) {
    backendInfo = " · code-only";
  }
  banner.innerHTML =
    `<span class="status-pill ${runState}">${runLabel}</span> `
    + `<span class="status-pill ${hp.cls}">${hp.label}</span>`
    + `${mcpPill} Graphify · local MCP server (isolated venv, no Docker)${portInfo}${pythonInfo}${countInfo}${backendInfo}`;
  statusSection.appendChild(banner);

  const explainer = document.createElement("p");
  explainer.className = "provider-meta";
  explainer.style.cssText = "margin: 4px 0 12px; opacity: 0.8;";
  explainer.textContent =
    "Self-hosted knowledge-graph MCP server. Setup installs graphify into an isolated venv (~/.fcc/graphify/venv); Start launches a local HTTP MCP process on 127.0.0.1 and registers it as a Claude Code MCP server (sibling of the MCP Router, not a backend inside it). No container and no cloud API key required — leave the transport key empty for loopback access.";
  statusSection.appendChild(explainer);

  if (status.last_error) {
    const errorBanner = document.createElement("div");
    errorBanner.className = "mcp-status-banner warning-banner";
    errorBanner.textContent = `Error: ${status.last_error}`;
    statusSection.appendChild(errorBanner);
  }

  const actions = document.createElement("div");
  actions.className = "mcp-action-row";

  const setupBtn = graphifyActionButton(
    "Setup",
    async () => {
      const result = await api("/admin/api/graphify/setup", { method: "POST" });
      showMessage(
        result.ready
          ? `Graphify ready — ${result.method} (${result.python})`
          : result.error || "Setup failed",
        result.ready ? "ok" : "error",
      );
      await loadGraphifyView();
    },
    "Install or verify graphify in an isolated venv (~/.fcc/graphify/venv)",
  );
  const startBtn = graphifyActionButton(
    "Start",
    async () => {
      const result = await api("/admin/api/graphify/start", { method: "POST" });
      showMessage(result.success ? "Graphify started" : result.error || "Start failed", result.success ? "ok" : "error");
      await loadGraphifyView();
    },
    "Launch the local Graphify MCP HTTP server and register it as a Claude Code MCP server",
  );
  const stopBtn = graphifyActionButton(
    "Stop",
    async () => {
      await api("/admin/api/graphify/stop", { method: "POST" });
      showMessage("Graphify stopped", "ok");
      await loadGraphifyView();
    },
    "Stop the local Graphify MCP server and unregister the Claude Code MCP entry",
  );
  const restartBtn = graphifyActionButton(
    "Restart",
    async () => {
      const result = await api("/admin/api/graphify/restart", { method: "POST" });
      showMessage(result.success ? "Graphify restarted" : "Restart failed", result.success ? "ok" : "error");
      await loadGraphifyView();
    },
    "Stop then start the local Graphify MCP server",
  );
  const refreshBtn = graphifyActionButton(
    "Refresh",
    async () => {
      await loadGraphifyView();
    },
    "Reload Graphify status, health, and projects",
  );

  actions.append(setupBtn, startBtn, stopBtn, restartBtn, refreshBtn);
  statusSection.appendChild(actions);

  const projectSection = document.createElement("section");
  projectSection.className = "settings-section";
  const projectHeading = document.createElement("div");
  projectHeading.className = "section-heading";
  projectHeading.innerHTML = `<div><h3>Projects</h3><p>Knowledge-graph projects tracked by Graphify.</p></div>`;
  projectSection.appendChild(projectHeading);

  const addRow = document.createElement("div");
  addRow.className = "mcp-action-row";
  addRow.style.cssText = "margin-bottom: 12px;";
  const pathInput = document.createElement("input");
  pathInput.type = "text";
  pathInput.placeholder = "Absolute repo path";
  pathInput.style.cssText = "flex: 1;";
  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "primary-button";
  addBtn.textContent = "Add Project";
  addBtn.addEventListener("click", async () => {
    const path = pathInput.value.trim();
    if (!path) return;
    await api("/admin/api/graphify/projects", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    pathInput.value = "";
    await loadGraphifyView();
  });
  addRow.append(pathInput, addBtn);
  projectSection.appendChild(addRow);

  // Queue banner: show when multiple items are in the index queue.
  const queueLength = status.index_queue_length ?? 0;
  if (queueLength > 0) {
    const queueBanner = document.createElement("div");
    queueBanner.className = "mcp-status-banner";
    const queueItems = status.index_queue || [];
    const current = queueItems.find((item) => item.status === "indexing");
    const queuedCount = queueLength - (current ? 1 : 0);
    const currentName = current
      ? (projects.find((p) => p.path === current.path)?.name || current.path)
      : "";
    let bannerText = '<span class="status-pill warn">Indexing</span> ';
    if (currentName) {
      bannerText += `<strong>${currentName}</strong> is indexing`;
    }
    if (queuedCount > 0) {
      bannerText += ` · ${queuedCount} project${queuedCount === 1 ? "" : "s"} queued`;
    }
    queueBanner.innerHTML = bannerText;
    projectSection.appendChild(queueBanner);
  }

  const grid = document.createElement("div");
  grid.className = "field-grid";
  projects.forEach((project) => {
    const card = document.createElement("article");
    card.className = "provider-card";

    const title = document.createElement("div");
    title.className = "provider-title";
    title.innerHTML = `<strong>${project.name || project.path}</strong>`;
    const pill = document.createElement("span");
    pill.className = `status-pill ${graphifyStatusPillClass(project.status)}`;
    pill.textContent = graphifyStatusLabel(project.status);
    if (project.status === "indexing") {
      const spinner = document.createElement("span");
      spinner.textContent = " ⟳";
      pill.appendChild(spinner);
    } else if (project.status === "queued") {
      const queueTag = document.createElement("span");
      queueTag.textContent = " ⏳";
      pill.appendChild(queueTag);
    }
    title.appendChild(pill);

    const meta = document.createElement("div");
    meta.className = "provider-meta";
    meta.textContent = project.path;
    const lastIndexed = document.createElement("div");
    lastIndexed.className = "provider-meta";
    lastIndexed.textContent = project.last_indexed
      ? `Last indexed: ${new Date(project.last_indexed).toLocaleString()}`
      : "Not indexed yet";

    const graphLine = document.createElement("div");
    graphLine.className = "provider-meta";
    graphLine.style.cssText = "opacity: 0.9;";
    if (project.status === "ready") {
      loadGraphSummary(graphifyPathB64(project.path), graphLine);
    }

    const errorLine = document.createElement("div");
    errorLine.className = "message-area error";
    errorLine.style.cssText = "display: none; margin-top: 4px; font-size: 0.85em;";
    if (project.status === "error" && project.error_message) {
      errorLine.textContent = project.error_message;
      errorLine.style.display = "block";
    }

    const cardActions = document.createElement("div");
    cardActions.className = "mcp-backend-actions";
    const indexBtn = document.createElement("button");
    indexBtn.type = "button";
    indexBtn.className = "secondary-button";
    indexBtn.textContent = "Index";
    indexBtn.addEventListener("click", async () => {
      indexBtn.disabled = true;
      const startedAt = Date.now();
      const pathB64 = graphifyPathB64(project.path);
      const setIndexingLabel = () => {
        const elapsed = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
        indexBtn.textContent = `Indexing… ${elapsed}s`;
      };
      setIndexingLabel();
      let pollInterval = null;
      try {
        const result = await api(`/admin/api/graphify/projects/${pathB64}/index`, {
          method: "POST",
          body: "{}",
        });
        if (
          !result.success ||
          result.status === "already_running" ||
          result.status === "already_queued"
        ) {
          showMessage(
            result.status === "already_running"
              ? "Indexing is already running"
              : result.status === "already_queued"
                ? "Project is already queued for indexing"
                : result.error || "Index failed",
            result.success ? "ok" : "error",
          );
        }
        pollInterval = setInterval(async () => {
          try {
            const task = await api(
              `/admin/api/graphify/projects/${pathB64}/index/status`,
            );
            if (!task) return;
            if (task.status === "indexing") {
              setIndexingLabel();
              return;
            }
            if (task.status === "queued") {
              const pos = task.queue_position || "?";
              indexBtn.textContent = `Queued (${pos})`;
              return;
            }
            clearInterval(pollInterval);
            pollInterval = null;
            if (task.status === "ready") {
              let detail = "";
              try {
                const summary = await api(
                  `/admin/api/graphify/projects/${pathB64}/graph`,
                );
                if (summary && summary.present) {
                  detail = ` — ${fmtNum(summary.node_count)} nodes · ${fmtNum(summary.link_count)} links`;
                }
              } catch {
                // ignore summary fetch failure
              }
              showMessage(`Indexed ${project.name || project.path}${detail}`, "ok");
            } else {
              showMessage(task.error_message || "Index failed", "error");
            }
            await loadGraphifyView();
          } catch (error) {
            clearInterval(pollInterval);
            pollInterval = null;
            showMessage(`Index status failed: ${error.message}`, "error");
            await loadGraphifyView();
          }
        }, 1000);
      } catch (error) {
        showMessage(`Index failed: ${error.message}`, "error");
      }
      // Only reset the button label when the interval has completed.
      if (!pollInterval) {
        indexBtn.disabled = false;
        indexBtn.textContent = "Index";
      }
    });

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "ghost-button";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", async () => {
      const pathB64 = graphifyPathB64(project.path);
      await api(`/admin/api/graphify/projects/${pathB64}`, { method: "DELETE" });
      await loadGraphifyView();
    });

    cardActions.append(indexBtn, removeBtn);
    card.append(title, meta, lastIndexed, graphLine, errorLine, cardActions);
    grid.appendChild(card);
  });
  projectSection.appendChild(grid);
  statusSection.appendChild(projectSection);

  container.appendChild(statusSection);
}

function graphifyActionButton(label, onClick, title) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "secondary-button";
  btn.textContent = label;
  if (title) btn.title = title;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    const original = btn.textContent;
    btn.textContent = `${label}...`;
    try {
      await onClick();
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  });
  return btn;
}

function graphifyPathB64(path) {
  const bytes = new TextEncoder().encode(path);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function onGraphifyViewActivated() {
  if (state.activeView === "graphify") {
    loadGraphifyView();
  } else {
    stopGraphifyAutoRefresh();
  }
}

// Load Freebuff view when its tab is activated
function onFreebuffViewActivated() {
  if (state.activeView === "freebuff") {
    loadFreebuffView();
  }
}

// Hook into setActiveView
const _originalSetActiveView = setActiveView;
setActiveView = function (viewId, opts) {
  _originalSetActiveView(viewId, opts);
  onMcpViewActivated();
  onFreebuffViewActivated();
  onGraphifyViewActivated();
};

load().catch((error) => {
  showMessage(error.message, "error");
});
