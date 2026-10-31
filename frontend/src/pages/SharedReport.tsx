import { useEffect, useState } from "react";
import { getSharedReport } from "../api";
import PublicShell from "../components/PublicShell";
import { formatDate } from "../format";
import type { SharedReportInfo } from "../types";

/** One report, opened from a link a person was given. No account, no navigation into the workspace. */
export default function SharedReport({ token }: { token: string | null }) {
  const [info, setInfo] = useState<SharedReportInfo | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "gone">(
    token ? "loading" : "gone",
  );

  useEffect(() => {
    document.title = "Shared security report – SecureScope";
    const robots = document.createElement("meta");
    robots.name = "robots";
    robots.content = "noindex, nofollow";
    document.head.appendChild(robots);
    return () => {
      robots.remove();
    };
  }, []);

  useEffect(() => {
    if (!token) return;
    let live = true;
    getSharedReport(token)
      .then((next) => {
        if (!live) return;
        setInfo(next);
        setState("ready");
      })
      .catch(() => {
        if (live) setState("gone");
      });
    return () => {
      live = false;
    };
  }, [token]);

  return (
    <PublicShell current={null}>
      <section className="sample-title" aria-labelledby="h-shared">
        <p className="landing-eyebrow">Website security report</p>
        <h1 id="h-shared">
          {state === "ready" && info ? info.host : "Shared security report"}
        </h1>
        {state === "loading" && <p className="muted">Opening the report…</p>}
        {state === "gone" && (
          <div className="card" role="alert">
            <p>
              This link is not valid. It may have expired, or the person who
              shared it may have turned it off. Ask them for a new link.
            </p>
          </div>
        )}
        {state === "ready" && info && (
          <div className="card shared-card">
            {info.prepared_by && (
              <p>
                Prepared by <strong>{info.prepared_by}</strong>
              </p>
            )}
            <dl className="sample-meta">
              <div>
                <dt>Scanned</dt>
                <dd>{formatDate(info.scanned_at)}</dd>
              </div>
              <div>
                <dt>Score</dt>
                <dd>
                  {info.score === null ? "–" : `${info.score} / 100`}
                  {info.grade ? ` (grade ${info.grade})` : ""}
                </dd>
              </div>
              <div>
                <dt>Link valid until</dt>
                <dd>{formatDate(info.expires_at)}</dd>
              </div>
            </dl>
            <a className="btn" href={info.download_path}>
              Open the PDF report
            </a>
            <p className="muted small">
              This report was made by SecureScope from passive checks of the
              website. It is a snapshot, not a guarantee, and not a penetration
              test.
            </p>
          </div>
        )}
      </section>
    </PublicShell>
  );
}
