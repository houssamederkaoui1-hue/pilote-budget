import { useApi } from "./useApi";
import type { HealthResponse } from "../types/api";

export function useHealth() {
  return useApi<HealthResponse>("/health");
}
