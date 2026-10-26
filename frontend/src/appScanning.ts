import { useEffect, useState } from "react";
import { appScanningAvailable } from "./api";

/** Whether App Scanning is switched on for this deployment (null while unknown). The server decides, and
 * answers 404 for everything while the feature is off; this only decides whether to show the menu entry. */
export function useAppScanningAvailable(
  organizationId: string | null,
  allowed: boolean,
): boolean | null {
  const [state, setState] = useState<{ org: string; value: boolean } | null>(
    null,
  );
  useEffect(() => {
    if (!organizationId || !allowed) return;
    let live = true;
    void appScanningAvailable().then((value) => {
      if (live) setState({ org: organizationId, value });
    });
    return () => {
      live = false;
    };
  }, [organizationId, allowed]);
  if (!allowed) return false;
  return state && state.org === organizationId ? state.value : null;
}
