import "@testing-library/jest-dom/vitest";

// We call cleanup() manually in each suite's afterEach; disable the
// library's global auto-cleanup afterEach to avoid double-unmount churn.
process.env.RTL_SKIP_AUTO_CLEANUP = "true";
