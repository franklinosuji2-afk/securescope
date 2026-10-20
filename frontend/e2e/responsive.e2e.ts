import { expect, test, type Page } from "@playwright/test";

/**
 * Every main screen, with deliberately long host names and URLs, at phone and tablet widths in both
 * themes: the page itself must never scroll sideways. (Stubbed API; layout only.)
 */
const LONG_HOST =
  "a-very-long-subdomain-name-for-layout-testing.staging.internal-services.example-company-name.org";
const user = {
  id: "u1",
  email: "a-quite-long-owner-address-for-testing@example-company-name.org",
  email_verified: true,
  organizations: [
    {
      id: "org1",
      name: "An Organisation With A Fairly Long Display Name",
      slug: "org",
      role: "OWNER",
    },
  ],
};
const token = "a".repeat(32);
const target = (hostname: string, status: "pending" | "verified") => ({
  id: hostname,
  hostname,
  status,
  challenge_token: token,
  challenge_expires_at: "2026-10-25T10:00:00Z",
  verified_at: status === "verified" ? "2026-10-18T10:00:00Z" : null,
  verification_method: status === "verified" ? "dns_txt" : null,
  last_check_at: null,
  last_check_error: null,
  created_at: "2026-10-18T09:00:00Z",
  dns_record_name: `_securescope-challenge.${hostname}`,
  dns_record_value: `securescope-verification=${token}`,
  http_file_url: `https://${hostname}/.well-known/securescope-verification.txt`,
  http_file_content: `securescope-verification=${token}`,
});
const lifecycle = {
  confidence: "high",
  fingerprint: "1".repeat(32),
  status: "open",
  status_note: null,
  first_seen_at: "2026-10-18T10:00:00Z",
  last_seen_at: "2026-10-18T12:00:00Z",
};
const top = {
  host: LONG_HOST,
  scan_id: "s1",
  finding_id: "SS-HDR-HSTS-001",
  title: "Strict-Transport-Security header is missing",
  severity: "high",
  confidence: "high",
  remediation: "Send 'Strict-Transport-Security: max-age=31536000'.",
};
const scan = {
  id: "s1",
  target_url: `https://${LONG_HOST}/some/very/long/path/that/keeps/going/on/and/on/index.html?with=query`,
  host: LONG_HOST,
  status: "completed",
  score: 84,
  grade: "B",
  created_at: "2026-10-18T12:00:00Z",
  finished_at: "2026-10-18T12:00:02Z",
  counts: { high: 1, info: 1 },
  error: null,
  metadata: {
    requested_url: `https://${LONG_HOST}/`,
    final_url: `https://${LONG_HOST}/`,
    host: LONG_HOST,
    resolved_addresses: ["2606:4700:4700:0000:0000:0000:0000:1111"],
    status_code: 200,
    content_type: "text/html; charset=utf-8",
    redirect_chain: [`https://${LONG_HOST}/`],
    off_origin_redirect: null,
    response_time_ms: 120,
    requests_made: 4,
    checks_run: ["https", "hsts", "tls-certificate", "exposed-files"],
    checks_skipped: [{ name: "security-txt", reason: "No usable answer." }],
    tls: {
      protocol: "TLSv1.3",
      cipher: "TLS_AES_256_GCM_SHA384",
      not_before: null,
      not_after: null,
      days_remaining: 80,
      issuer: "Google Trust Services",
      subject: null,
      verified: true,
    },
  },
  score_note: "Heuristic score.",
  findings: [
    {
      id: "SS-HDR-HSTS-001",
      title: "Strict-Transport-Security header is missing",
      severity: "high",
      category: "Security headers",
      description: "Without HSTS, browsers may still attempt plain HTTP.",
      evidence: `Checked https://${LONG_HOST}/some/very/long/path/that/keeps/going/index.html and content-security-policy: default-src 'self'; style-src 'self' 'unsafe-inline'`,
      remediation: "Send the header.",
      ...lifecycle,
    },
  ],
};
const summary = { ...scan, findings: undefined, metadata: undefined };
const overview = {
  sites: [
    {
      host: LONG_HOST,
      latest_scan_id: "s1",
      score: 84,
      grade: "B",
      scanned_at: "2026-10-18T12:00:00Z",
      previous_score: 76,
      score_change: 8,
      open_counts: { high: 1 },
      open_total: 1,
      top_finding: top,
      history: [
        { scan_id: "s0", score: 60, scanned_at: "2026-10-16T12:00:00Z" },
        { scan_id: "s1", score: 84, scanned_at: "2026-10-18T12:00:00Z" },
      ],
    },
  ],
  fix_first: top,
  other_open: 0,
};

async function stub(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    let body: unknown = { items: [], total: 0 };
    if (url.endsWith("/auth/me")) body = user;
    else if (url.includes("/targets"))
      body = {
        items: [
          target(LONG_HOST, "verified"),
          target(`new.${LONG_HOST}`, "pending"),
        ],
      };
    else if (url.includes("/overview")) body = overview;
    else if (url.includes("/audit-events"))
      body = {
        items: [
          {
            id: "e1",
            timestamp: "2026-10-18T12:00:00Z",
            event_type: "scan.created",
            actor_email: user.email,
            target: LONG_HOST,
            detail: { url: scan.target_url },
          },
        ],
        total: 1,
        event_types: ["scan.created"],
      };
    else if (url.includes("/organizations/"))
      body = {
        ...user.organizations[0],
        members: [
          {
            user_id: "u1",
            email: user.email,
            role: "OWNER",
            joined_at: "2026-10-18T09:00:00Z",
          },
        ],
      };
    else if (url.includes("/scans/s1")) body = scan;
    else if (url.includes("/scans")) body = { items: [summary], total: 1 };
    await route.fulfill({ json: body });
  });
}

const ROUTES = [
  ["overview", "/#/"],
  ["targets", "/#/targets"],
  ["findings", "/#/findings?scan=s1"],
  ["finding", "/#/findings?scan=s1&finding=SS-HDR-HSTS-001"],
  ["history", "/#/history"],
  ["scan", "/#/history?scan=s1"],
  ["team", "/#/team"],
  ["audit", "/#/audit"],
  ["analytics", "/#/analytics"],
  ["health", "/#/health"],
  ["privacy", "/#/privacy"],
] as const;

for (const width of [360, 390, 768]) {
  for (const scheme of ["dark", "light"] as const) {
    test(`no sideways page scroll at ${width}px (${scheme})`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: scheme });
      await stub(page);
      const wide: string[] = [];
      const tall: string[] = [];
      for (const [name, path] of ROUTES) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await page.waitForTimeout(150);
        const overflow = await page.evaluate(
          () =>
            document.documentElement.scrollWidth -
            document.documentElement.clientWidth,
        );
        if (overflow > 0) wide.push(`${name} (+${overflow}px)`);
        const rail = page.locator("aside.rail");
        if (width < 861 && (await rail.count()) > 0) {
          // The collapsed top bar must keep its own height, however short the page is.
          const bar = await rail.evaluate(
            (el) => el.getBoundingClientRect().height,
          );
          if (bar > 90) tall.push(`${name} (bar ${Math.round(bar)}px)`);
        }
        if (process.env.SHOTS)
          await page.screenshot({
            path: `test-results/shots/${name}-${width}-${scheme}.png`,
            fullPage: true,
          });
      }
      expect(wide, "screens that scroll sideways").toEqual([]);
      expect(tall, "screens with a stretched top bar").toEqual([]);
    });
  }
}
