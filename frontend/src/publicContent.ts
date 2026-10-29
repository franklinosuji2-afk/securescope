/**
 * Copy for the public pages. It used to sit on the home page; it now lives on the page where a visitor
 * looks for it (What we check, Pricing, Help, App Scanning Early Access). The wording is unchanged.
 */

export const PROBLEMS = [
  {
    icon: "eye",
    title: "Easy to overlook",
    text: "A missing header, a cookie anyone's script can read, a forgotten .env file. None of it looks broken, so nobody notices until someone else does.",
  },
  {
    icon: "file",
    title: "Hard to read",
    text: "Big scanners can bury the two real problems under pages of jargon. You close the tab and promise yourself you'll come back.",
  },
  {
    icon: "users",
    title: "Hard to prove",
    text: "A client asks whether their site is secure. “I think so” is not an answer, and you have nothing to hand them.",
  },
];

export const NUMBERS = [
  { value: "0", label: "attack payloads sent. Ever." },
  { value: "9", label: "areas checked on every scan" },
  { value: "4", label: "steps from sign-up to your first scan" },
  { value: "3", label: "free scans every month" },
];

export const BENEFITS = [
  {
    icon: "proof",
    title: "Catch the quick wins",
    text: "Most findings are a one-line setting. You fix them in minutes, not sprints.",
  },
  {
    icon: "chart",
    title: "Know what to fix first",
    text: "Findings are ranked by severity, and your Overview points at the one to do next.",
  },
  {
    icon: "doc",
    title: "Show your work",
    text: "Hand a client a clear PDF that says what was checked, what passed and what changed since last time.",
  },
  {
    icon: "lock",
    title: "Stay on the safe side",
    text: "Only sites you have proven you own can be scanned, and the scan only reads what any visitor could.",
  },
];

export const CHECKS = [
  {
    title: "HTTPS and redirects",
    icon: "lock",
    text: "Is the site served over HTTPS, and does plain HTTP send visitors there?",
  },
  {
    title: "Security headers",
    icon: "layers",
    text: "HSTS, Content-Security-Policy, X-Content-Type-Options, Referrer-Policy and Permissions-Policy: present, and not set so weakly they do nothing.",
  },
  {
    title: "Cookies",
    icon: "cookie",
    text: "Session cookies without Secure, HttpOnly or SameSite are flagged, with the cookie named.",
  },
  {
    title: "TLS certificate",
    icon: "cert",
    text: "Valid for the host name, trusted, and not about to expire.",
  },
  {
    title: "Exposed files",
    icon: "file",
    text: "A readable .env file, public .git metadata, directory listings, and a missing security.txt contact.",
  },
  {
    title: "Information leaks",
    icon: "eye",
    text: "Server and X-Powered-By headers that announce software and version numbers to anyone who asks.",
  },
  {
    title: "Page content",
    icon: "doc",
    text: "Scripts and forms loaded over plain HTTP on an HTTPS page, and third-party scripts with no integrity check.",
  },
  {
    title: "Cross-origin access",
    icon: "users",
    text: "CORS headers that let any website read logged-in responses, or trust the “null” origin.",
  },
  {
    title: "Email and DNS",
    icon: "log",
    text: "SPF, DMARC, CAA and DNSSEC records on your main domain, so spoofed mail and mis-issued certificates are harder.",
  },
];

export const STEPS = [
  {
    title: "Add your site",
    text: "Enter the host name you want checked.",
  },
  {
    title: "Prove it is yours",
    text: "Add a DNS TXT record or upload a small file. Only verified sites can be scanned.",
  },
  {
    title: "Run a scan",
    text: "A handful of ordinary page requests. No attack traffic, and it usually finishes within a minute.",
  },
  {
    title: "Review and fix",
    text: "Each finding shows the evidence and how to fix it. Scan again to see it marked resolved.",
  },
  {
    title: "Share a report",
    text: "Download a PDF, or export the data, to show what was checked and what changed.",
  },
];

export const FEATURES = [
  {
    title: "A score you can follow",
    icon: "chart",
    text: "One grade per site, with a severity breakdown and a history so you can see whether things are getting better.",
  },
  {
    title: "Evidence on every finding",
    icon: "proof",
    text: "The URL, status and headers that were actually seen, and whether a result was observed or a heuristic.",
  },
  {
    title: "Findings with a lifecycle",
    icon: "cycle",
    text: "Mark a finding as accepted risk or false positive with a note. It only counts as resolved when a later scan no longer sees it.",
  },
  {
    title: "Reports you can hand over",
    icon: "doc",
    text: "Download a PDF, or export HTML, Markdown, JSON or CSV. Reports say what was checked, what passed and where the scan stops.",
  },
  {
    title: "Built for clients",
    icon: "users",
    text: "On the Agency plan, invite clients as read-only viewers so they see results without being able to change anything.",
  },
  {
    title: "An audit trail",
    icon: "log",
    text: "Owners and admins can see who did what in the workspace, with filters.",
  },
];

export const APP_STEPS = [
  {
    icon: "folder",
    title: "Add your project",
    text: "Create a project for the application you want to assess.",
  },
  {
    icon: "scan",
    title: "Analyse supported manifests",
    text: "Upload package-lock.json, package.json or requirements.txt. The files are read, never run.",
  },
  {
    icon: "review",
    title: "Review findings and coverage",
    text: "See what was found, what was checked and what could not be.",
  },
  {
    icon: "fix",
    title: "Investigate and remediate",
    text: "Each finding names the package and, where the source provides it, a fixed version.",
  },
];

export const APP_WORKS = [
  "Reading supported dependency manifests",
  "Listing the packages and exact versions they declare",
  "Recording a result as completed, incomplete or failed, never guessed",
];
export const APP_PLANNED = [
  "Connecting the vulnerability database (a licence and privacy review comes first)",
  "Code analysis (SAST)",
  "Secret detection",
  "Downloadable App Scanning reports",
];

// Illustrative only: not a real scan, not real customer data.
export const APP_PREVIEW = [
  {
    pkg: "example-library 1.2.0",
    finding: "Known vulnerability (illustrative)",
    severity: "High",
    sev: "high",
    status: "Completed",
  },
  {
    pkg: "another-package ^2.0.0",
    finding: "Not checked: the version is a range, not an exact version",
    severity: "Not rated",
    sev: "info",
    status: "Skipped",
  },
  {
    pkg: "Whole run",
    finding: "Vulnerability source unavailable: no result is reported",
    severity: "Not rated",
    sev: "info",
    status: "Incomplete",
  },
];

export const FAQ_GROUPS = [
  {
    title: "About SecureScope",
    items: [
      {
        q: "Who is SecureScope for?",
        a: "People who look after websites they own or are responsible for: freelancers, small teams and agencies that want a clear, repeatable check of the basics, with something to show a client. It does not replace a penetration test or a security team.",
      },
      {
        q: "Is this a penetration test?",
        a: "No. It checks the basics that are visible from outside, such as headers, cookies, HTTPS and exposed files. A clean result does not mean a site is secure, and every report says what was not checked.",
      },
      {
        q: "What is App Scanning, and can I use it?",
        a: "App Scanning will check the dependency files of an application for known vulnerabilities. It is in Early Access, which means it is still in development and not open to the public: the vulnerability database is not connected yet, so it cannot report vulnerabilities today. Website Scanning is the product available now.",
      },
    ],
  },
  {
    title: "Safety and permission",
    items: [
      {
        q: "Is it safe to run on my site?",
        a: "Yes. SecureScope only reads: a few normal page requests, requests for a few well-known paths such as /.env to see whether they are publicly readable, and one TLS connection. It sends no exploit payloads, no brute force and no port scans, and it never stores page contents.",
      },
      {
        q: "Can I scan a site that isn't mine?",
        a: "No. Every site has to be verified with a DNS record or a file first, so SecureScope is not a tool for testing other people's websites. Verification proves technical control of the domain; if it is not your own site you also need the owner's permission.",
      },
    ],
  },
  {
    title: "Monitoring and your data",
    items: [
      {
        q: "What does scheduled monitoring do?",
        a: "On the Professional and Agency plans (not on sale yet) SecureScope scans a verified site daily or weekly and emails you only when something new appears or the score drops by 5 points or more, so a change that opens a gap does not go unnoticed for months.",
      },
      {
        q: "Where is my data?",
        a: "Scan results are kept for as long as your plan allows (30, 90 or 365 days) and then deleted. You can delete your account and its data yourself. See the privacy notice for details.",
      },
    ],
  },
];

/** One plain-language question per check, shown before the technical detail. */
export const CHECK_PLAIN: Record<string, string> = {
  "HTTPS and redirects": "Does your site use a secure connection?",
  "Security headers":
    "Does your site ask browsers to switch on their built-in protections?",
  Cookies: "Are login cookies protected from being read or misused?",
  "TLS certificate":
    "Is your site's security certificate valid, and not about to run out?",
  "Exposed files": "Are any private files accidentally public?",
  "Information leaks": "Does your server announce which software it runs?",
  "Page content": "Does a secure page load anything over an unsafe connection?",
  "Cross-origin access": "Can other websites read data they should not?",
  "Email and DNS": "Could someone send email pretending to be you?",
};
