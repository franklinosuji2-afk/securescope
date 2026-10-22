// A side-by-side comparison of what each plan includes. Every row describes something that exists in the
// product today; ideas that are not built yet are listed separately and labelled as planned.

type Cell = boolean | string;
type Row = { label: string; free: Cell; pro: Cell; agency: Cell };
type Group = { title: string; rows: Row[] };

const GROUPS: Group[] = [
  {
    title: "Safe, passive scanning",
    rows: [
      {
        label: "Ownership of the site is verified before any scan",
        free: true,
        pro: true,
        agency: true,
      },
      {
        label: "HTTPS and TLS certificate checks",
        free: true,
        pro: true,
        agency: true,
      },
      {
        label: "Security headers (HSTS, CSP and more)",
        free: true,
        pro: true,
        agency: true,
      },
      {
        label:
          "Cookie flags, exposed .git and .env files, version disclosure, directory listing, security.txt",
        free: true,
        pro: true,
        agency: true,
      },
      {
        label: "Never sends attack or exploit traffic",
        free: true,
        pro: true,
        agency: true,
      },
    ],
  },
  {
    title: "Results you can act on",
    rows: [
      {
        label: "Health score and A to F grade",
        free: true,
        pro: true,
        agency: true,
      },
      {
        label: "Plain-language fix steps with platform examples",
        free: true,
        pro: true,
        agency: true,
      },
      {
        label: "Ready-made prompt for your AI coding assistant",
        free: true,
        pro: true,
        agency: true,
      },
      {
        label: "Mark findings as accepted risk or false positive",
        free: true,
        pro: true,
        agency: true,
      },
      {
        label: "Score history for each site",
        free: true,
        pro: true,
        agency: true,
      },
      {
        label: "Compare two scans and see what changed",
        free: true,
        pro: true,
        agency: true,
      },
      {
        label: "PDF report and data export (HTML, Markdown, JSON, CSV)",
        free: true,
        pro: true,
        agency: true,
      },
    ],
  },
  {
    title: "Teams and agencies",
    rows: [
      {
        label: "Invite teammates and clients",
        free: false,
        pro: false,
        agency: true,
      },
      {
        label: "Client list with private notes and a dashboard",
        free: false,
        pro: false,
        agency: true,
      },
      {
        label: "Your agency name on PDF reports",
        free: false,
        pro: false,
        agency: true,
      },
      {
        label: "Expiring, revocable report share links",
        free: false,
        pro: false,
        agency: true,
      },
    ],
  },
  {
    title: "Limits",
    rows: [
      { label: "Websites", free: "1", pro: "5", agency: "20" },
      {
        label: "Scans per month",
        free: "3",
        pro: "30",
        agency: "150",
      },
      {
        label: "Scan history kept",
        free: "30 days",
        pro: "90 days",
        agency: "365 days",
      },
    ],
  },
];

const PLANNED = [
  "Scheduled scans",
  "Email alerts when a scan finds something new",
  "API and webhooks",
];

const NOT_OFFERED = [
  "Active exploit scanners (ZAP, Nuclei, OpenVAS) or port scanning",
  "Scans behind a login, or of internal networks",
  "Compliance attestations such as SOC 2",
  "Single sign-on (SAML)",
];

function Value({ value }: { value: Cell }) {
  if (typeof value === "string") return <>{value}</>;
  return value ? (
    <>
      <span aria-hidden="true" className="cmp-yes">
        ✓
      </span>
      <span className="visually-hidden">Included</span>
    </>
  ) : (
    <>
      <span aria-hidden="true" className="cmp-no">
        –
      </span>
      <span className="visually-hidden">Not included</span>
    </>
  );
}

export default function PlanComparison() {
  return (
    <div className="cmp">
      <h3 id="h-compare">What each plan includes</h3>
      <p className="muted small">
        Everything marked here exists today. Professional and Agency are not on
        sale yet.
      </p>
      <div
        className="cmp-scroll"
        role="region"
        aria-labelledby="h-compare"
        tabIndex={0}
      >
        <table className="cmp-table">
          <thead>
            <tr>
              <th scope="col">Feature</th>
              <th scope="col">Free</th>
              <th scope="col">Professional</th>
              <th scope="col">Agency</th>
            </tr>
          </thead>
          {GROUPS.map((g) => (
            <tbody key={g.title}>
              <tr className="cmp-group">
                <th scope="colgroup" colSpan={4}>
                  {g.title}
                </th>
              </tr>
              {g.rows.map((r) => (
                <tr key={r.label}>
                  <th scope="row">{r.label}</th>
                  <td>
                    <Value value={r.free} />
                  </td>
                  <td>
                    <Value value={r.pro} />
                  </td>
                  <td>
                    <Value value={r.agency} />
                  </td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
      <div className="cmp-notes">
        <section className="card" aria-labelledby="h-planned">
          <h4 id="h-planned">Planned, not available yet</h4>
          <ul>
            {PLANNED.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </section>
        <section className="card" aria-labelledby="h-notoffered">
          <h4 id="h-notoffered">What SecureScope does not do</h4>
          <ul>
            {NOT_OFFERED.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
          <p className="muted small">
            It is built to be safe to run against any site you own, every time.
          </p>
        </section>
      </div>
    </div>
  );
}
