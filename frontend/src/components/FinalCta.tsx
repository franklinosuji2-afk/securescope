import { buildHash } from "../router";

/** The closing call to action on the public pages. */
export default function FinalCta() {
  return (
    <section className="landing-final card">
      <h2>Check your first site in a few minutes</h2>
      <p className="muted">
        Create a free account, verify your site and run your first scan.
      </p>
      <a className="btn" href={buildHash("register", null)}>
        Create free account
      </a>
    </section>
  );
}
