import { useAuth } from "../auth";
import BentoGrid from "../components/bento/BentoGrid";
import Posture from "../components/Posture";
import ScanForm from "../components/ScanForm";
import ScanView from "../components/ScanView";
import SetupGuide from "../components/SetupGuide";
import SummaryCards from "../components/SummaryCards";
import { ErrorNotice, Loading } from "../components/ui";
import { setupSteps } from "../overview";
import { buildHash, type Route } from "../router";
import { canManageTargets, canScan } from "../types";
import { useOverviewData } from "../useOverviewData";
import { useScan } from "../useScan";

export default function Overview({
  route,
  onStarted,
}: {
  route: Route;
  onStarted: (id: string) => void;
}) {
  const { scan, loading, error, reload } = useScan(route.scanId);
  const { organization } = useAuth();
  const role = organization?.role;
  const allowed = role ? canScan(role) : false;
  const data = useOverviewData(`${route.scanId ?? ""}:${scan?.status ?? ""}`);

  const scanned = data.overview.sites.length > 0;
  const showGuide = !data.loading && !data.error && !scanned && !route.scanId;
  const verifiedHosts = data.targets
    .filter((t) => t.status === "verified")
    .map((t) => t.hostname);

  return (
    <div className="stack">
      <header className="page-head">
        <h1>Overview</h1>
        {role === "VIEWER" ? (
          <p>
            The security status of the sites shared with you, with the latest
            results and downloadable reports. Passive, non-exploitative checks
            of headers, cookies and basic exposure. This is not a penetration
            test.
          </p>
        ) : (
          <p>
            Where your sites stand and what to do next. Passive,
            non-exploitative checks of headers, cookies and basic exposure for
            sites you own or are authorized to test. This is not a penetration
            test.
          </p>
        )}
      </header>
      {data.loading && <Loading label="Loading your sites…" />}
      {data.error && <ErrorNotice message={data.error} />}
      {showGuide && (
        <SetupGuide
          steps={setupSteps(
            data.targets,
            scanned,
            role ? canManageTargets(role) : false,
          )}
        />
      )}
      {scanned && (
        <SummaryCards overview={data.overview} targets={data.targets} />
      )}
      {scanned && (
        <BentoGrid
          overview={data.overview}
          targets={data.targets}
          refreshKey={`${route.scanId ?? ""}:${scan?.status ?? ""}`}
          canManage={role ? canManageTargets(role) : false}
          canRun={allowed}
          organizationId={organization?.id ?? null}
        />
      )}
      <div className={scanned ? "overview-grid" : "stack"}>
        {scanned && (
          <Posture
            overview={data.overview}
            onScanAgain={allowed ? onStarted : undefined}
            showFixFirst={false}
          />
        )}
        {allowed ? (
          <ScanForm onStarted={onStarted} verifiedHosts={verifiedHosts} />
        ) : (
          <div className="notice notice-info" role="note">
            Your role ({role ?? "none"}) can view scans and export reports but
            cannot start scans.
          </div>
        )}
      </div>
      {error && <ErrorNotice message={error} />}
      {loading && !scan && <Loading label="Loading scan…" />}
      {scan && (
        <ScanView
          scan={scan}
          onChanged={allowed ? reload : undefined}
          onRetried={allowed ? onStarted : undefined}
          onDeleted={
            allowed
              ? () => {
                  window.location.hash = buildHash("overview", null);
                }
              : undefined
          }
        />
      )}
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
