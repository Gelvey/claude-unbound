import { api } from "./client";
import type { ModuleTab } from "../types";

export function getModuleTabs(): Promise<{ tabs: ModuleTab[] }> {
  return api("/admin/api/modules/tabs");
}
