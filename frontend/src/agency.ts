import { useEffect, useState } from "react";
import { agencyAvailable } from "./api";

/** Whether the active workspace's plan includes client workspaces (null while unknown). The server decides;
 * this only decides what to show. */
export function useAgencyAvailable(
  organizationId: string | null,
  allowed: boolean,
): boolean | null {
  const [state, setState] = useState<{
    org: string | null;
    value: boolean;
  } | null>(null);
  useEffect(() => {
    if (!organizationId || !allowed) return;
    let live = true;
    void agencyAvailable().then((value) => {
      if (live) setState({ org: organizationId, value });
    });
    return () => {
      live = false;
    };
  }, [organizationId, allowed]);
  if (!allowed) return false;
  return state && state.org === organizationId ? state.value : null;
}
