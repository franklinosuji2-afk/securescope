import { useAuth } from "../auth";
import ScanForm from "../components/ScanForm";
import ScanView from "../components/ScanView";
import { EmptyState, ErrorNotice, Loading } from "../components/ui";
import type { Route } from "../router";
import { canScan } from "../types";
import { useScan } from "../useScan";

export default function Overview({ route, onStarted }: { route: Route; onStarted: (id: string) => void }) {
  const { scan, loading, error } = useScan(route.scanId);
  const { organization } = useAuth();
  const allowed = organization ? canScan(organization.role) : false;
  return (
    <div className="stack">
      <header className="page-head">
        <h1>Overview</h1>
        <p>
          Passive, non-exploitative checks of headers, cookies and basic exposure for sites you own or are authorized
          to test. This is not a penetration test.
        </p>
      </header>
      {allowed ? (
        <ScanForm onStarted={onStarted} />
      ) : (
        <div className="notice notice-info" role="note">
          Your role ({organization?.role ?? "none"}) can view scans and export reports but cannot start scans.
        </div>
      )}
      {error && <ErrorNotice message={error} />}
      {loading && !scan && <Loading label="Loading scan…" />}
      {scan && <ScanView scan={scan} />}
      {!route.scanId && (
        <EmptyState title="No scan yet">
          Enter a URL you are authorized to test and confirm the acknowledgement. Results will appear here – nothing is
          shown until a real scan has run.
        </EmptyState>
      )}
    </div>
  );
}
