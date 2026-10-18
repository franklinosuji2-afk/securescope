import { useAuth } from "../auth";
import Posture from "../components/Posture";
import ScanForm from "../components/ScanForm";
import ScanView from "../components/ScanView";
import SetupGuide from "../components/SetupGuide";
import { ErrorNotice, Loading } from "../components/ui";
import { fixFirst, hasCompletedScan, setupSteps, siteSummaries } from "../overview";
import { buildHash, type Route } from "../router";
import { canManageTargets, canScan } from "../types";
import { useOverviewData } from "../useOverviewData";
import { useScan } from "../useScan";

export default function Overview({ route, onStarted }: { route: Route; onStarted: (id: string) => void }) {
  const { scan, loading, error } = useScan(route.scanId);
  const { organization } = useAuth();
  const role = organization?.role;
  const allowed = role ? canScan(role) : false;
  const data = useOverviewData(`${route.scanId ?? ""}:${scan?.status ?? ""}`);

  const sites = siteSummaries(data.targets, data.scans);
  const scanned = hasCompletedScan(data.scans);
  const showGuide = !data.loading && !data.error && !scanned && !route.scanId;
  const verifiedHosts = data.targets.filter((t) => t.status === "verified").map((t) => t.hostname);
  const fix = fixFirst(sites.map((s) => data.details[s.latest.id]).filter((d) => d !== undefined));

  return (
    <div className="stack">
      <header className="page-head">
        <h1>Overview</h1>
        <p>
          Where your sites stand and what to do next. Passive, non-exploitative checks of headers, cookies and basic
          exposure for sites you own or are authorized to test. This is not a penetration test.
        </p>
      </header>
      {data.loading && <Loading label="Loading your sites…" />}
      {data.error && <ErrorNotice message={data.error} />}
      {showGuide && <SetupGuide steps={setupSteps(data.targets, data.scans, role ? canManageTargets(role) : false)} />}
      {scanned && <Posture sites={sites} details={data.details} fix={fix} />}
      {allowed ? (
        <ScanForm onStarted={onStarted} verifiedHosts={verifiedHosts} />
      ) : (
        <div className="notice notice-info" role="note">
          Your role ({role ?? "none"}) can view scans and export reports but cannot start scans.
        </div>
      )}
      {error && <ErrorNotice message={error} />}
      {loading && !scan && <Loading label="Loading scan…" />}
      {scan && <ScanView scan={scan} />}
      {scan?.status === "completed" && (
        <p>
          <a className="btn btn-link" href={buildHash("findings", scan.id)}>
            {scan.findings.length === 0
              ? "See what was checked"
              : `Review ${scan.findings.length} finding${scan.findings.length === 1 ? "" : "s"}`}
          </a>
        </p>
      )}
    </div>
  );
}
