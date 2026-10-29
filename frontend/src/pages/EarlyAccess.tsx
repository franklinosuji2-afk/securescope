import FinalCta from "../components/FinalCta";
import { HomeProducts } from "../components/HomeHero";
import { Icon } from "../components/LandingIcon";
import PublicShell from "../components/PublicShell";
import {
  APP_PLANNED,
  APP_PREVIEW,
  APP_STEPS,
  APP_WORKS,
} from "../publicContent";
import { buildHash } from "../router";

function scrollTo(id: string) {
  const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  document
    .getElementById(id)
    ?.scrollIntoView({ behavior: calm ? "auto" : "smooth" });
}

/**
 * What App Scanning is, what works today and what is still planned. It is in Early Access and says so; the
 * wording moved here unchanged from the home page.
 */
export default function EarlyAccess() {
  const register = buildHash("register", null);
  return (
    <PublicShell current="early-access">
      <section
        className="sample-title agency-hero"
        aria-labelledby="h-early-access"
      >
        <p className="landing-eyebrow">App Scanning</p>
        <h1 id="h-early-access">App Scanning is in Early Access</h1>
        <p className="landing-lead">
          Early Access means availability is limited and some parts are still
          being built. Website Scanning is the product you can use today.
        </p>
      </section>
      <div className="landing-body">
        <HomeProducts
          register={register}
          onApp={() => scrollTo("app-scanning")}
          planned={APP_PLANNED}
          works={APP_WORKS}
        />
        <section
          id="app-scanning"
          className="landing-section"
          aria-labelledby="h-app-scanning"
        >
          <p className="landing-eyebrow">
            App Scanning · Early Access · In development
          </p>
          <h2 id="h-app-scanning">
            Dependency security, explained before it is switched on
          </h2>
          <p className="landing-sub muted">
            Early Access means App Scanning is not generally available: access
            is limited, there is no waiting list yet, and parts are still being
            built. This is how it is designed to work, and what it will and will
            not tell you.
          </p>
          <ol className="landing-steps">
            {APP_STEPS.map((st, i) => (
              <li key={st.title} className="card">
                <Icon name={st.icon} />
                <span className="landing-step-no" aria-hidden="true">
                  {i + 1}
                </span>
                <h3>{st.title}</h3>
                <p className="muted">{st.text}</p>
              </li>
            ))}
          </ol>
          <ul className="landing-honest">
            <li>
              Only supported files and exact package versions are assessed.
            </li>
            <li>Unsupported or unpinned dependencies may remain unchecked.</li>
            <li>
              If the vulnerability source is unavailable the result is
              incomplete or failed. It is never reported as clean.
            </li>
            <li>
              It is not a penetration test, and uploaded code is never executed.
            </li>
          </ul>

          <h3 className="landing-subhead" id="h-app-preview">
            What a result looks like
          </h3>
          <div className="landing-table-wrap">
            <table
              className="landing-table"
              aria-describedby="app-preview-note"
            >
              <caption className="visually-hidden">
                Illustrative App Scanning results
              </caption>
              <thead>
                <tr>
                  <th scope="col">Package</th>
                  <th scope="col">Finding</th>
                  <th scope="col">Severity</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {APP_PREVIEW.map((r) => (
                  <tr key={r.pkg}>
                    <th scope="row" data-label="Package">
                      {r.pkg}
                    </th>
                    <td data-label="Finding">{r.finding}</td>
                    <td data-label="Severity">
                      <span className={`sev sev-${r.sev}`}>{r.severity}</span>
                    </td>
                    <td data-label="Status">
                      <strong>{r.status}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p id="app-preview-note" className="landing-fineprint muted small">
            Illustrative example with made-up package names. It is not a real
            scan and not customer data. Severity is shown only when the
            vulnerability source provides it.
          </p>

          <h3 className="landing-subhead" id="h-app-privacy">
            Privacy and trust
          </h3>
          <div className="landing-grid landing-trust">
            <article className="card landing-card">
              <h4>Website Scanning</h4>
              <p className="muted">
                Reads what any visitor could read from a site you have verified
                you own, and never stores page contents.
              </p>
            </article>
            <article className="card landing-card">
              <h4>App Scanning</h4>
              <p className="muted">
                Uploaded files are read in memory. SecureScope keeps findings,
                file names, package names and versions, and file digests, not
                file contents.
              </p>
            </article>
            <article className="card landing-card">
              <h4>Not yet decided</h4>
              <p className="muted">
                The vulnerability database is not connected. What would be sent
                to it is reviewed first, and the privacy notice is updated
                before App Scanning opens.
              </p>
            </article>
          </div>
          <p className="landing-fineprint muted small">
            See the <a href="#/privacy">privacy notice</a> and the{" "}
            <a href="#/terms">terms</a>.
          </p>
        </section>

        <FinalCta />
      </div>
    </PublicShell>
  );
}
