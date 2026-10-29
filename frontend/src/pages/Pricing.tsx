import FinalCta from "../components/FinalCta";
import PlanComparison from "../components/PlanComparison";
import PublicShell from "../components/PublicShell";
import { buildHash } from "../router";

/** The plans. The paid plans are not on sale yet and the page says so. */
export default function Pricing() {
  const register = buildHash("register", null);
  return (
    <PublicShell current="pricing">
      <section className="sample-title agency-hero" aria-labelledby="h-pricing">
        <p className="landing-eyebrow">Plans</p>
        <h1 id="h-pricing">Pricing</h1>
        <p className="landing-lead">
          Start free. The paid plans are not on sale yet; they will be announced
          here.
        </p>
      </section>
      <div className="landing-body">
        <section id="pricing" className="landing-section" aria-label="Plans">
          <div className="landing-grid landing-plans">
            <article className="card landing-plan-live">
              <h3>
                Free <span className="landing-badge">Available now</span>
              </h3>
              <p className="landing-price">€0</p>
              <ul>
                <li>1 website</li>
                <li>3 scans per month</li>
                <li>Scan history kept 30 days</li>
                <li>PDF and data exports</li>
                <li>Optional public score badge</li>
              </ul>
              <div className="landing-plan-foot">
                <a className="btn" href={register}>
                  Create free account
                </a>
                <p className="muted small landing-plan-note">Available now.</p>
              </div>
            </article>
            <article className="card landing-plan-soon">
              <h3>
                Professional{" "}
                <span className="landing-badge soon">Coming soon</span>
              </h3>
              <p className="landing-price">
                €19 <span className="muted small">/ month</span>
              </p>
              <ul>
                <li>5 websites</li>
                <li>30 scans per month</li>
                <li>Scan history kept 90 days</li>
                <li>Scheduled scans with email and webhook alerts</li>
                <li>GitHub Action and API tokens for CI</li>
                <li>PDF and data exports</li>
              </ul>
              <div className="landing-plan-foot">
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => {
                    const calm = window.matchMedia?.(
                      "(prefers-reduced-motion: reduce)",
                    ).matches;
                    document
                      .getElementById("h-compare")
                      ?.scrollIntoView({ behavior: calm ? "auto" : "smooth" });
                  }}
                >
                  Compare plans
                </button>
                <p className="muted small landing-plan-note">
                  Not on sale yet.
                </p>
              </div>
            </article>
            <article className="card landing-plan-soon">
              <h3>
                Agency <span className="landing-badge soon">Coming soon</span>
              </h3>
              <p className="landing-price">
                €49 <span className="muted small">/ month</span>
              </p>
              <ul>
                <li>20 websites</li>
                <li>150 scans per month</li>
                <li>Scan history kept 365 days</li>
                <li>Scheduled scans with email and webhook alerts</li>
                <li>GitHub Action and API tokens for CI</li>
                <li>Invite team members and clients</li>
                <li>Client dashboard, branded PDFs, share links</li>
              </ul>
              <div className="landing-plan-foot">
                <a className="btn-ghost" href="#/agency-features">
                  Explore Agency features
                </a>
                <p className="muted small landing-plan-note">
                  Not on sale yet.
                </p>
              </div>
            </article>
          </div>
          <PlanComparison />
          <p className="muted small">
            Prices are planned and may change before launch. If you reach a
            limit, nothing is deleted; you just can&apos;t add more until the
            month renews.
          </p>
        </section>
        <FinalCta />
      </div>
    </PublicShell>
  );
}
