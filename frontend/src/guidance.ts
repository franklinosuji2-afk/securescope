/**
 * Explanatory guidance for each finding type. This is static, reviewed text keyed by the scanner's
 * finding id; it never contains scan data. Anything observed about a target comes from the backend.
 */
export interface Guidance {
  impact: string;
  detection: "observed" | "heuristic";
  detectionNote: string;
  fixExample?: { label: string; code: string };
  verify: string;
  references: { label: string; url: string }[];
  limitations: string;
}

const MDN = "https://developer.mozilla.org/en-US/docs/Web/HTTP";
const HEADER_LIMIT =
  "SecureScope reads the headers of one response from the address that was scanned. Other pages, error pages and API routes can send different headers.";
const HEADER_VERIFY =
  "Run curl -sI <your URL> (or open the browser developer tools, Network tab) and check the header is in the response. Then run a new scan; the finding is only treated as resolved when a later scan no longer reports it.";

const FIND: Record<string, Guidance> = {
  "SS-TLS-001": {
    impact:
      "Anyone on the network path can read or change the page, including login forms and cookies, before it reaches the visitor.",
    detection: "observed",
    detectionNote:
      "The final URL after redirects used http:// instead of https://.",
    fixExample: {
      label: "nginx: redirect HTTP to HTTPS",
      code: "server {\n  listen 80;\n  server_name example.com;\n  return 301 https://$host$request_uri;\n}",
    },
    verify:
      "Open the http:// address in a browser or run curl -sI http://<host> and confirm it answers with a 301 redirect to https://.",
    references: [
      {
        label: "MDN: Transport Layer Security",
        url: "https://developer.mozilla.org/en-US/docs/Web/Security/Transport_Layer_Security",
      },
    ],
    limitations:
      "TLS certificate validity and cipher configuration are not assessed by SecureScope.",
  },
  "SS-TLS-002": {
    impact:
      "None by itself. This is the desired behaviour; HSTS makes it stronger because browsers then skip the plain HTTP request.",
    detection: "observed",
    detectionNote:
      "The scan started at an http:// address and was redirected to https://.",
    verify: "No action needed.",
    references: [
      {
        label: "MDN: Strict-Transport-Security",
        url: `${MDN}/Headers/Strict-Transport-Security`,
      },
    ],
    limitations: "Only the scanned address was tested.",
  },
  "SS-HDR-HSTS-001": {
    impact:
      "Browsers may still try plain HTTP on a visit, which allows downgrade and protocol-stripping attacks on hostile networks.",
    detection: "observed",
    detectionNote:
      "No Strict-Transport-Security header was present in the HTTPS response.",
    fixExample: {
      label: "Cloudflare Pages or Netlify _headers file",
      code: "/*\n  Strict-Transport-Security: max-age=31536000; includeSubDomains",
    },
    verify: HEADER_VERIFY,
    references: [
      {
        label: "MDN: Strict-Transport-Security",
        url: `${MDN}/Headers/Strict-Transport-Security`,
      },
    ],
    limitations: `${HEADER_LIMIT} Only add includeSubDomains once every subdomain works over HTTPS.`,
  },
  "SS-HDR-HSTS-002": {
    impact:
      "A short lifetime means browsers stop enforcing HTTPS sooner, which leaves a longer window for downgrade attacks.",
    detection: "observed",
    detectionNote: "The HSTS max-age value was below 180 days.",
    fixExample: {
      label: "Recommended value",
      code: "Strict-Transport-Security: max-age=31536000; includeSubDomains",
    },
    verify: HEADER_VERIFY,
    references: [
      {
        label: "MDN: Strict-Transport-Security",
        url: `${MDN}/Headers/Strict-Transport-Security`,
      },
    ],
    limitations: HEADER_LIMIT,
  },
  "SS-HDR-CSP-001": {
    impact:
      "Without a Content-Security-Policy, a cross-site scripting flaw anywhere on the page is easier to exploit because the browser has no limit on where scripts may load from.",
    detection: "observed",
    detectionNote: "No Content-Security-Policy header was present.",
    fixExample: {
      label: "Starter policy (test in report-only mode first)",
      code: "Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    },
    verify: `${HEADER_VERIFY} After deploying, check the browser console for blocked resources.`,
    references: [{ label: "MDN: Content-Security-Policy", url: `${MDN}/CSP` }],
    limitations: `${HEADER_LIMIT} SecureScope does not judge whether a policy is complete, only whether it is present and avoids unsafe script sources.`,
  },
  "SS-HDR-CSP-002": {
    impact:
      "'unsafe-inline' or 'unsafe-eval' lets injected inline scripts run, which removes much of the protection a CSP gives against cross-site scripting.",
    detection: "observed",
    detectionNote:
      "The script policy contained 'unsafe-inline' or 'unsafe-eval'.",
    fixExample: {
      label: "Use a per-response nonce instead",
      code: "Content-Security-Policy: script-src 'self' 'nonce-<random per response>'\n<script nonce=\"<same value>\">…</script>",
    },
    verify: `${HEADER_VERIFY} Confirm the page still works with the stricter policy.`,
    references: [{ label: "MDN: Content-Security-Policy", url: `${MDN}/CSP` }],
    limitations:
      "Static sites that need inline scripts may have to accept this trade-off or generate script hashes at build time.",
  },
  "SS-HDR-XCTO-001": {
    impact:
      "Browsers may guess a file's type from its content, which can make some uploaded or misconfigured files run as scripts.",
    detection: "observed",
    detectionNote: "X-Content-Type-Options was missing or not 'nosniff'.",
    fixExample: { label: "Header", code: "X-Content-Type-Options: nosniff" },
    verify: HEADER_VERIFY,
    references: [
      {
        label: "MDN: X-Content-Type-Options",
        url: `${MDN}/Headers/X-Content-Type-Options`,
      },
    ],
    limitations: HEADER_LIMIT,
  },
  "SS-HDR-REF-001": {
    impact:
      "Without a policy, the full URL of the page, including any query string, may be sent to other sites when visitors follow links.",
    detection: "observed",
    detectionNote: "No Referrer-Policy header was present.",
    fixExample: {
      label: "Header",
      code: "Referrer-Policy: strict-origin-when-cross-origin",
    },
    verify: HEADER_VERIFY,
    references: [
      { label: "MDN: Referrer-Policy", url: `${MDN}/Headers/Referrer-Policy` },
    ],
    limitations: `${HEADER_LIMIT} Browsers already apply a safe default today, so this is a hardening step.`,
  },
  "SS-HDR-PERM-001": {
    impact:
      "Low. A Permissions-Policy lets you switch off browser features such as camera or location that the site does not use, limiting what injected or embedded code can ask for.",
    detection: "observed",
    detectionNote: "No Permissions-Policy header was present.",
    fixExample: {
      label: "Header",
      code: "Permissions-Policy: camera=(), microphone=(), geolocation=()",
    },
    verify: HEADER_VERIFY,
    references: [
      {
        label: "MDN: Permissions-Policy",
        url: `${MDN}/Headers/Permissions-Policy`,
      },
    ],
    limitations: HEADER_LIMIT,
  },
  "SS-DISC-SRV-001": {
    impact:
      "A version number helps an attacker pick known exploits for that exact software.",
    detection: "observed",
    detectionNote: "The Server header contained a version number.",
    verify:
      "Run curl -sI <your URL> and confirm the Server header no longer shows a version.",
    references: [
      {
        label: "OWASP Secure Headers Project",
        url: "https://owasp.org/www-project-secure-headers/",
      },
    ],
    limitations:
      "Hiding a version does not fix vulnerabilities. Keep the software patched.",
  },
  "SS-DISC-SRV-002": {
    impact:
      "Very low. The server names its software, which is mildly useful to an attacker. Many hosting providers set this and it cannot be changed.",
    detection: "observed",
    detectionNote: "A Server header was present without a version number.",
    verify: "Only relevant if you control the web server or proxy.",
    references: [
      {
        label: "OWASP Secure Headers Project",
        url: "https://owasp.org/www-project-secure-headers/",
      },
    ],
    limitations:
      "On managed platforms (for example a CDN) the header may not be configurable.",
  },
  "SS-DISC-XPB-001": {
    impact:
      "Reveals the framework or runtime in use, which helps an attacker target known weaknesses.",
    detection: "observed",
    detectionNote: "An X-Powered-By header was present.",
    fixExample: {
      label: "Express (Node.js)",
      code: "app.disable('x-powered-by');",
    },
    verify: "Run curl -sI <your URL> and confirm X-Powered-By is gone.",
    references: [
      {
        label: "OWASP Secure Headers Project",
        url: "https://owasp.org/www-project-secure-headers/",
      },
    ],
    limitations:
      "Removing the header hides information; it does not fix vulnerabilities.",
  },
  "SS-COOKIE-SECURE-001": {
    impact:
      "Cookies without Secure can be sent over plain HTTP, where a network attacker can read them, including session cookies.",
    detection: "observed",
    detectionNote:
      "At least one Set-Cookie header had no Secure attribute. Cookie values are never read or stored.",
    fixExample: {
      label: "Cookie attributes",
      code: "Set-Cookie: session=<value>; Secure; HttpOnly; SameSite=Lax; Path=/",
    },
    verify:
      "Load the page and check Set-Cookie in the response headers, or the Application tab in browser developer tools.",
    references: [
      { label: "MDN: Set-Cookie", url: `${MDN}/Headers/Set-Cookie` },
    ],
    limitations:
      "Only cookies set on the scanned response are seen. Cookies set after login or on other pages are not tested.",
  },
  "SS-COOKIE-HTTPONLY-001": {
    impact:
      "Scripts can read cookies without HttpOnly, so a cross-site scripting flaw could steal a session cookie.",
    detection: "observed",
    detectionNote: "At least one Set-Cookie header had no HttpOnly attribute.",
    fixExample: {
      label: "Cookie attributes",
      code: "Set-Cookie: session=<value>; Secure; HttpOnly; SameSite=Lax; Path=/",
    },
    verify: "Check Set-Cookie in the response headers after the change.",
    references: [
      { label: "MDN: Set-Cookie", url: `${MDN}/Headers/Set-Cookie` },
    ],
    limitations:
      "Cookies that scripts legitimately need to read (for example a theme preference) do not need HttpOnly. It matters most for session cookies.",
  },
  "SS-COOKIE-SAMESITE-001": {
    impact:
      "Without an explicit SameSite value the browser default applies, which weakens protection against cross-site request forgery in some browsers.",
    detection: "observed",
    detectionNote: "At least one Set-Cookie header had no SameSite attribute.",
    fixExample: {
      label: "Cookie attributes",
      code: "Set-Cookie: session=<value>; Secure; HttpOnly; SameSite=Lax; Path=/",
    },
    verify: "Check Set-Cookie in the response headers after the change.",
    references: [
      { label: "MDN: Set-Cookie", url: `${MDN}/Headers/Set-Cookie` },
    ],
    limitations: "Only cookies set on the scanned response are seen.",
  },
  "SS-DIR-001": {
    impact:
      "A generated directory index can expose files that were never meant to be public, such as backups or configuration.",
    detection: "heuristic",
    detectionNote:
      "The page body matched the markup that web servers generate for directory listings. This is a signature match, not a confirmed exposure. Review the page manually.",
    fixExample: { label: "nginx", code: "autoindex off;" },
    verify:
      "Open the URL in a browser. If it lists files, disable indexing and confirm the page no longer lists them.",
    references: [
      {
        label: "CWE-548: Exposure of Information Through Directory Listing",
        url: "https://cwe.mitre.org/data/definitions/548.html",
      },
    ],
    limitations:
      "A normal page that happens to look like a directory index can match. Compressed responses are not inspected.",
  },
  "SS-SCOPE-001": {
    impact:
      "None. SecureScope stopped because the site redirected somewhere you have not verified.",
    detection: "observed",
    detectionNote: "The response redirected to a different site.",
    verify:
      "Verify and scan the destination directly if you are authorized to test it.",
    references: [],
    limitations: "SecureScope only follows redirects within the same site.",
  },
};

const GENERIC: Guidance = {
  impact: "See the description for what was observed and why it matters.",
  detection: "observed",
  detectionNote: "Reported by a passive check of the scanned response.",
  verify:
    "Apply the recommended fix, then run a new scan. The finding is only treated as resolved when a later scan no longer reports it.",
  references: [],
  limitations:
    "SecureScope runs a limited set of passive checks on a single page.",
};

export function guidanceFor(findingId: string): Guidance {
  return FIND[findingId] ?? GENERIC;
}
