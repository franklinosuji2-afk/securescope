import { buildHash } from "../router";

/** Shown for an address the app does not know, instead of silently landing on Overview. */
export default function NotFound() {
  return (
    <div className="stack">
      <header className="page-head">
        <h1>Page not found</h1>
        <p>This address does not match any page in SecureScope.</p>
      </header>
      <div className="card empty">
        <h2>Nothing here</h2>
        <p>
          The link may be mistyped or out of date.{" "}
          <a href={buildHash("overview", null)}>Go to Overview</a>
        </p>
      </div>
    </div>
  );
}
