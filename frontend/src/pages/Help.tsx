import FinalCta from "../components/FinalCta";
import PublicShell from "../components/PublicShell";
import { FAQ_GROUPS } from "../publicContent";

/** Questions and answers, plus where to go for anything else. */
export default function Help() {
  return (
    <PublicShell current="help">
      <section className="sample-title agency-hero" aria-labelledby="h-help">
        <p className="landing-eyebrow">Help</p>
        <h1 id="h-help">Questions</h1>
        <p className="landing-lead">
          Short answers about what SecureScope does, what it will not do, and
          what happens to your data.
        </p>
      </section>
      <div className="landing-body">
        <section className="landing-section" aria-label="Questions and answers">
          <div className="landing-faq">
            {FAQ_GROUPS.map((g, i) => (
              <section
                key={g.title}
                className={`faq-group faq-group-${i + 1}`}
                aria-labelledby={`faq-g${i}`}
              >
                <h2 id={`faq-g${i}`}>{g.title}</h2>
                {g.items.map((f) => (
                  <details key={f.q}>
                    <summary>{f.q}</summary>
                    <p className="muted">{f.a}</p>
                  </details>
                ))}
              </section>
            ))}
          </div>
        </section>
        <section className="landing-section" aria-labelledby="h-more-help">
          <h2 id="h-more-help">More help</h2>
          <ul className="landing-honest">
            <li>
              Contact details for questions and data requests are in the{" "}
              <a href="#/impressum">Impressum</a> and the{" "}
              <a href="#/privacy">privacy notice</a>.
            </li>
            <li>
              To report a security problem in SecureScope itself, use the
              contact in <a href="/.well-known/security.txt">security.txt</a>.
            </li>
            <li>
              What each check means, and how a scan works, is on{" "}
              <a href="#/checks">What we check</a>.
            </li>
          </ul>
        </section>
        <FinalCta />
      </div>
    </PublicShell>
  );
}
