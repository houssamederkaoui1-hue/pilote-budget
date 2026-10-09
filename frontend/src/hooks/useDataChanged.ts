import { useEffect } from "react";

import { subscribeDataChanged } from "../lib/refresh";
import type { ApiState } from "./useApi";

/**
 * Re-fetches the given API states whenever a global data-change is broadcast
 * (e.g. Quick Add posted a transaction from another page). Keeps hooks' own
 * reload caching, just triggers them on demand.
 */
export function useDataChangedReload(...states: Array<ApiState<unknown>>): void {
  useEffect(() => subscribeDataChanged(() => {
    states.forEach((state) => state.reload());
  }), states);
}