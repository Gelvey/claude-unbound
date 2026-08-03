import { useState } from "react";
import { AdminStoreProvider, useAdminStore } from "./store/useAdminStore";
import { ThemeProvider, useTheme } from "./theme/ThemeProvider";
import { ModelOptionsDatalist, CopyButton } from "./components/Field";
import { AdminViews } from "./views/AdminViews";
import { ModuleTabView } from "./components/ModuleTabsLoader";

function BrandMark() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      width="32"
      height="32"
      className="drop-shadow-[0_4px_14px_rgba(91,141,239,0.25)]"
    >
      <title>Claude Unbound</title>
      <g fill="#5B8DEF">
        <rect x="28" y="4" width="8" height="56" rx="4" ry="4" />
        <rect x="28" y="4" width="8" height="56" rx="4" ry="4" transform="rotate(45 32 32)" />
        <rect x="28" y="4" width="8" height="56" rx="4" ry="4" transform="rotate(90 32 32)" />
        <rect x="28" y="4" width="8" height="56" rx="4" ry="4" transform="rotate(135 32 32)" />
        <rect x="28" y="4" width="8" height="56" rx="4" ry="4" transform="rotate(180 32 32)" />
        <rect x="28" y="4" width="8" height="56" rx="4" ry="4" transform="rotate(225 32 32)" />
        <rect x="28" y="4" width="8" height="56" rx="4" ry="4" transform="rotate(270 32 32)" />
        <rect x="28" y="4" width="8" height="56" rx="4" ry="4" transform="rotate(315 32 32)" />
      </g>
    </svg>
  );
}

function Sidebar({ onNavigate }: { onNavigate: () => void }) {
  const { views, activeView, setActiveView } = useAdminStore();
  const { toggleTheme } = useTheme();
  return (
    <aside className="sidebar bg-base-100 border-r border-base-300 sticky top-0 h-screen flex flex-col gap-1 p-6 w-[268px] shrink-0">
      <div className="flex items-center gap-3 mb-6 pb-5 border-b border-base-300">
        <BrandMark />
        <div>
          <h1 className="text-[15px] font-bold leading-tight">Claude Unbound</h1>
          <p className="text-xs uppercase tracking-wide font-semibold text-base-content/60">
            Server Control
          </p>
        </div>
      </div>
      <nav className="grid gap-2" aria-label="Admin views">
        {views.map((view) => (
          <button
            key={view.id}
            type="button"
            className={`text-left px-3 py-2.5 rounded-lg font-bold text-[13px] border border-transparent ${
              activeView === view.id
                ? "bg-base-300 text-base-content border-l-[3px] border-l-primary"
                : "text-base-content/60 hover:text-base-content hover:bg-base-300"
            }`}
            aria-current={activeView === view.id ? "page" : undefined}
            onClick={() => {
              setActiveView(view.id);
              onNavigate();
            }}
          >
            {view.label}
          </button>
        ))}
      </nav>
      <button
        type="button"
        className="btn btn-sm btn-ghost rounded-lg mt-auto justify-start"
        onClick={toggleTheme}
      >
        Toggle theme
      </button>
    </aside>
  );
}

function Topbar() {
  const { views, activeView } = useAdminStore();
  const active = views.find((v) => v.id === activeView) || views[0];
  return (
    <header className="mb-7 pb-5 border-b border-base-300">
      <h2 className="text-2xl font-extrabold tracking-tight">{active?.title ?? ""}</h2>
    </header>
  );
}

function ActionBar() {
  const { dirtyCount, totalCount, applyDisabled, apply, validate, message, configPath } =
    useAdminStore();
  const dirtyLabel =
    dirtyCount === 0
      ? `${totalCount} settings saved`
      : `${dirtyCount} unsaved change${dirtyCount === 1 ? "" : "s"} of ${totalCount}`;
  const messageClass =
    message.kind === "error"
      ? "text-error"
      : message.kind === "ok"
        ? "text-success"
        : "text-base-content/60";
  return (
    <footer className="fixed right-0 bottom-0 left-[268px] z-10 grid [grid-template-columns:minmax(0,1fr)_minmax(180px,auto)_auto] gap-3.5 items-center min-h-[76px] border-t border-base-300 bg-base-100/90 px-9 py-3.5 backdrop-blur-xl">
      <div className="grid gap-0.5 min-w-0">
        <strong className="overflow-hidden text-ellipsis whitespace-nowrap text-sm">
          {dirtyLabel}
        </strong>
        <span className="overflow-hidden text-ellipsis whitespace-nowrap text-xs text-base-content/60 flex items-center gap-2">
          {configPath}
          <CopyButton target={configPath} />
        </span>
      </div>
      <div className={`min-w-0 text-sm ${messageClass}`}>{message.text}</div>
      <div className="flex gap-2">
        <button
          type="button"
          className="btn btn-sm btn-neutral rounded-lg"
          onClick={() => void validate(true)}
        >
          Validate
        </button>
        <button
          type="button"
          className="btn btn-sm btn-primary rounded-lg"
          disabled={applyDisabled}
          title="Save all settings to the env file"
          onClick={() => void apply()}
        >
          Apply
        </button>
      </div>
      <div className="text-[11px] text-base-content/60 text-center col-span-full">
        Saves all settings to the env file, including defaults
      </div>
    </footer>
  );
}

function Shell() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { activeView, views, moduleTabs } = useAdminStore();
  const activeModuleTab = views.find((v) => v.id === activeView && v.moduleTab);
  const activeTabData = activeModuleTab
    ? moduleTabs.find((t) => t.id === activeModuleTab.id)
    : undefined;

  return (
    <div className="grid [grid-template-columns:268px_minmax(0,1fr)] min-h-screen pb-[86px]">
      <div className="md:hidden fixed top-3 left-3 z-[200]">
        <button
          type="button"
          className="btn btn-sm btn-ghost rounded-lg w-10 h-10 p-0 text-xl"
          aria-label="Toggle sidebar"
          onClick={() => setSidebarOpen((v) => !v)}
        >
          ☰
        </button>
      </div>
      <div
        className={`fixed top-0 left-0 z-[150] transition-transform duration-200 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        } md:static md:translate-x-0`}
      >
        <Sidebar onNavigate={() => setSidebarOpen(false)} />
      </div>
      <main className="min-w-0 p-8 md:pt-20 md:px-9">
        <Topbar />
        <div className="grid gap-5">
          {activeTabData ? <ModuleTabView tab={activeTabData} /> : <AdminViews />}
        </div>
      </main>
      <ActionBar />
      <ModelOptionsDatalist />
    </div>
  );
}

export function App() {
  return (
    <ThemeProvider>
      <AdminStoreProvider>
        <Shell />
      </AdminStoreProvider>
    </ThemeProvider>
  );
}
