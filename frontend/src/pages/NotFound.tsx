import type { ReactNode } from "react";
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

/** Shown for a page that exists but is not open to this workspace or role, instead of an empty screen. */
export function Unavailable({
  title,
  children,
  link,
}: {
  title: string;
  children: ReactNode;
  link?: { href: string; label: string };
}) {
  return (
    <div className="stack">
      <header className="page-head">
        <h1>{title}</h1>
      </header>
      <div className="card empty">
        <h2>Not available here</h2>
        <p>
          {children}
          {link && (
            <>
              {" "}
              <a href={link.href}>{link.label}</a>
            </>
          )}
        </p>
      </div>
    </div>
  );
}
