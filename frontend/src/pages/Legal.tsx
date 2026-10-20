import type { ReactNode } from "react";
import type { Page } from "../router";
import { buildHash } from "../router";

// Legal text for the operator. Update these constants if the operator's details change.
const OPERATOR = "Franklin Chinonso Osuji";
// TODO before sharing the site publicly: replace with an office or forwarding address that can receive post.
const STREET = "[Service address to be added]";
const CITY = "Berlin";
const EMAIL = "franklin.c.osuji@gmx.de";
const UPDATED = "20 October 2026";

function Doc({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="auth-wrap">
      <div className="card auth-card" style={{ maxWidth: 720 }}>
        <p className="small">
          <a href={buildHash("login", null)}>&larr; Back to SecureScope</a>
        </p>
        <h1>{title}</h1>
        {children}
        <p className="muted small">Last updated: {UPDATED}</p>
        <LegalLinks />
      </div>
    </div>
  );
}

export function LegalLinks() {
  return (
    <p className="small legal-links">
      <a href="#/impressum">Impressum</a> &middot;{" "}
      <a href="#/privacy">Privacy</a> &middot; <a href="#/terms">Terms</a>
    </p>
  );
}

function Impressum() {
  return (
    <Doc title="Impressum">
      <h2>Information according to § 5 DDG</h2>
      <p>
        {OPERATOR}
        <br />
        {STREET}
        <br />
        {CITY}
        <br />
        Germany
      </p>
      <h2>Contact</h2>
      <p>
        Email: <a href={`mailto:${EMAIL}`}>{EMAIL}</a>
      </p>
      <h2>Responsible for content (§ 18 Abs. 2 MStV)</h2>
      <p>{OPERATOR}, address as above.</p>
      <h2>Disclaimer</h2>
      <p>
        SecureScope runs passive, heuristic checks. Its results are guidance and
        are not a penetration test, a security certification or a guarantee that
        a site is free of vulnerabilities.
      </p>
    </Doc>
  );
}

function Privacy() {
  return (
    <Doc title="Privacy notice">
      <h2>Who is responsible</h2>
      <p>
        {OPERATOR}, {STREET}, {CITY}, Germany. Contact:{" "}
        <a href={`mailto:${EMAIL}`}>{EMAIL}</a>.
      </p>

      <h2>What we store and why</h2>
      <ul>
        <li>
          <strong>Account data:</strong> your email address, a salted hash of
          your password (never the password itself) and your workspace name.
          Needed to provide your account (Art. 6(1)(b) GDPR).
        </li>
        <li>
          <strong>Scan data:</strong> the domains you add, the ownership
          verification status, scan results and reports. Needed to provide the
          service (Art. 6(1)(b) GDPR). Scan results are deleted automatically
          after a retention period (currently 30 days).
        </li>
        <li>
          <strong>Audit log and security data:</strong> actions in your
          workspace and, for abuse and rate limiting, your IP address, kept only
          as long as needed. Our legitimate interest in keeping the service
          secure (Art. 6(1)(f) GDPR).
        </li>
        <li>
          <strong>Emails:</strong> we send only service emails such as email
          confirmation and password reset. No marketing.
        </li>
      </ul>

      <h2>Cookies</h2>
      <p>
        One session cookie (<code>ss_session</code>) keeps you signed in. It is
        strictly necessary, so no consent banner is needed. We use no
        advertising or tracking cookies and no analytics.
      </p>

      <h2>Service providers (processors)</h2>
      <ul>
        <li>
          Cloudflare, Inc. &ndash; hosting of the website and request routing.
        </li>
        <li>
          Render Services, Inc. &ndash; hosting of the application server.
        </li>
        <li>Neon, Inc. &ndash; database hosting.</li>
        <li>Brevo (Sendinblue SAS), France &ndash; sending service emails.</li>
      </ul>
      <p>
        Some providers are based in the USA or may process data there. Transfers
        rely on the EU-US Data Privacy Framework or standard contractual
        clauses.
      </p>

      <h2>Your rights</h2>
      <p>
        You can ask for access, correction, deletion, restriction or export of
        your data, and object to processing based on legitimate interest. To
        delete your account and its data, email us. You can also complain to a
        supervisory authority, for Berlin the Berliner Beauftragte für
        Datenschutz und Informationsfreiheit.
      </p>

      <h2>Scanning other people&apos;s sites</h2>
      <p>
        SecureScope sends ordinary web requests to domains you have verified as
        yours. It does not scan domains whose ownership has not been verified.
      </p>
    </Doc>
  );
}

function Terms() {
  return (
    <Doc title="Terms of use">
      <h2>1. What SecureScope is</h2>
      <p>
        SecureScope runs passive, heuristic security checks on websites and
        explains the results. It is not a penetration test, an audit or a
        guarantee of security.
      </p>
      <h2>2. Only scan what you own</h2>
      <p>
        You may add and scan only domains that you own or are explicitly
        authorized to test. You must prove control of each domain through the
        verification step. Using SecureScope against systems you are not
        authorized to test is forbidden and may be illegal.
      </p>
      <h2>3. Your account</h2>
      <p>
        Keep your password private and do not share your account. You are
        responsible for activity in your workspace. We may suspend accounts that
        abuse the service.
      </p>
      <h2>4. No guarantees</h2>
      <p>
        The service is provided as is, during an early access phase, without
        guarantee of availability or completeness of findings. Checks can miss
        issues or report false positives. Decisions based on the results are
        yours.
      </p>
      <h2>5. Liability</h2>
      <p>
        We are liable without limit for intent, gross negligence and injury to
        life, body or health, and as required by mandatory law. For slight
        negligence we are liable only for breach of essential contractual duties
        and only for foreseeable, typical damage.
      </p>
      <h2>6. Changes and contact</h2>
      <p>
        We may update these terms; the date above shows the latest version.
        Questions: <a href={`mailto:${EMAIL}`}>{EMAIL}</a>.
      </p>
    </Doc>
  );
}

export default function LegalPage({ page }: { page: Page }) {
  if (page === "privacy") return <Privacy />;
  if (page === "terms") return <Terms />;
  return <Impressum />;
}
