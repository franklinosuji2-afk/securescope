import { useEffect, useState } from "react";
import * as api from "../api";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import ApiTokens from "../components/ApiTokens";
import ScoreBadges from "../components/ScoreBadges";
import WebhookAlerts from "../components/WebhookAlerts";
import { ErrorNotice, Loading } from "../components/ui";
import type { Target } from "../types";
import { canManageMembers, canManageTargets } from "../types";
import "../integrations.css";

/** Alerts, badges and API access, kept apart from the list of domains on the Targets page. */
export default function Integrations() {
  const { organization } = useAuth();
  const orgId = organization?.id ?? null;
  const [targets, setTargets] = useState<Target[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const manage = organization ? canManageTargets(organization.role) : false;

  useEffect(() => {
    let cancelled = false;
    if (orgId) {
      api
        .listTargets()
        .then((items) => !cancelled && setTargets(items))
        .catch(
          (err: unknown) =>
            !cancelled &&
            setError(
              err instanceof ApiError ? err.message : "Could not load sites.",
            ),
        );
    }
    return () => {
      cancelled = true;
    };
  }, [orgId]);

  const hasVerified = !!targets && targets.some((t) => t.status === "verified");

  return (
    <div className="stack ig">
      <header className="page-head">
        <h1>Integrations</h1>
        <p>
          Send alerts to a webhook or Slack, show a score badge on your own
          site, and let CI use the API. Domains and scheduled scans stay on the
          Targets page.
        </p>
      </header>
      {error && <ErrorNotice message={error} />}
      {!targets && !error && <Loading label="Loading integrations…" />}
      {targets && !hasVerified && (
        <div className="notice notice-info" role="status">
          Alerts and badges need at least one verified site.{" "}
          <a href="#/targets">Go to Targets</a> to add and verify a domain.
        </div>
      )}
      {hasVerified && <WebhookAlerts manage={manage} />}
      {hasVerified && <ScoreBadges manage={manage} />}
      {organization && canManageMembers(organization.role) && <ApiTokens />}
    </div>
  );
}
