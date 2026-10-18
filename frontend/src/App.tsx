import type { Page } from "./router";
import { buildHash, useRoute } from "./router";
import Findings from "./pages/Findings";
import History from "./pages/History";
import Overview from "./pages/Overview";

const NAV: { page: Page; label: string }[] = [
  { page: "overview", label: "Overview" },
  { page: "findings", label: "Findings" },
  { page: "history", label: "Scan History" },
];

export default function App() {
  const [route, navigate] = useRoute();
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="rail">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
            <path d="M16 3 5 7v8c0 7 4.6 11.7 11 14 6.4-2.3 11-7 11-14V7L16 3Z" fill="none" stroke="#6d4aff" strokeWidth="2.2" />
            <path d="m11 16 4 4 6-8" fill="none" stroke="#2dd4bf" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          SecureScope
        </div>
        <nav className="nav" aria-label="Primary">
          {NAV.map((n) => (
            <a
              key={n.page}
              href={buildHash(n.page, n.page === "history" ? null : route.scanId)}
              aria-current={route.page === n.page ? "page" : undefined}
            >
              {n.label}
            </a>
          ))}
        </nav>
        <p className="rail-note">Heuristic, passive checks only. Not a penetration test.</p>
      </aside>
      <main className="main" id="main" tabIndex={-1}>
        {route.page === "overview" && <Overview route={route} onStarted={(id) => navigate("overview", id)} />}
        {route.page === "findings" && <Findings route={route} />}
        {route.page === "history" && <History onOpen={(id) => navigate("findings", id)} />}
      </main>
    </div>
  );
}
