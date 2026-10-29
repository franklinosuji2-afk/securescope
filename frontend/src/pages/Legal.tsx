import BrandMark from "../components/BrandMark";
import { CornerThemeToggle } from "../components/ThemeToggle";
import type { ReactNode } from "react";
import type { Page } from "../router";
import { useAuth } from "../auth";
import { CONTACT, mailto, type ContactKind } from "../contact";
import { buildHash } from "../router";

// Legal text for the operator. Update these constants if the operator's details change.
const OPERATOR = "Franklin Chinonso Osuji";
// LAUNCH BLOCKER: the operator's postal address is deliberately NOT published.
// § 5 DDG expects a serviceable postal address, so this Impressum is incomplete
// until the operator supplies a compliant address solution. Do not invent one,
// and do not promote the site publicly before this is resolved.
const UPDATED = "29 October 2026";

const TABS: { page: Page; label: string }[] = [
  { page: "impressum", label: "Impressum" },
  { page: "privacy", label: "Privacy" },
  { page: "terms", label: "Terms" },
];

function Mail({ kind }: { kind: ContactKind }) {
  return <a href={mailto(kind)}>{CONTACT[kind]}</a>;
}

function Doc({
  page,
  title,
  children,
}: {
  page: Page;
  title: string;
  children: ReactNode;
}) {
  const { user } = useAuth();
  const home = user ? buildHash("overview", null) : buildHash("login", null);
  return (
    <div className="auth-wrap legal-wrap">
      <CornerThemeToggle />
      <div className="legal-shell">
        <header className="legal-head">
          <a className="legal-brand" href={home}>
            <BrandMark className="brand-mark" shield="var(--accent)" />
            SecureScope
          </a>
          <a className="small" href={home}>
            {user ? "Back to the app" : "Back to sign in"}
          </a>
        </header>
        <nav className="legal-tabs" aria-label="Legal pages">
          {TABS.map((t) => (
            <a
              key={t.page}
              href={`#/${t.page}`}
              aria-current={t.page === page ? "page" : undefined}
            >
              {t.label}
            </a>
          ))}
        </nav>
        <div className="card legal-card">
          <h1>{title}</h1>
          {children}
          <p className="muted small">Last updated: {UPDATED}</p>
        </div>
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
    <Doc page="impressum" title="Impressum">
      <h2>Information according to § 5 DDG</h2>
      <p>
        {OPERATOR}
        <br />
        Postal address: not currently published.
      </p>
      <h2>Contact</h2>
      <p>
        Email: <Mail kind="general" />
      </p>
      <ul>
        <li>
          Questions about the service: <Mail kind="support" />
        </li>
        <li>
          Privacy and data requests: <Mail kind="privacy" />
        </li>
        <li>
          Security reports: <Mail kind="security" />
        </li>
      </ul>
      <p>
        SecureScope is operated by an individual. It is not a registered
        company.
      </p>
      <h2>Responsible for content (§ 18 Abs. 2 MStV)</h2>
      <p>{OPERATOR}. Contact: see the email addresses above.</p>
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
    <Doc page="privacy" title="Privacy notice">
      <p className="legal-summary">
        <strong>The short version:</strong> we store your account and scan data
        only to run SecureScope, we use two strictly necessary cookies (plus a
        short-lived one only while you sign in with Google or GitHub), we count
        visits to the public pages without cookies or stored IP addresses, we
        never sell data, and you can ask us to delete everything.
      </p>
      <h2>Who is responsible</h2>
      <p>
        {OPERATOR}, Germany. Contact for privacy questions and data requests:{" "}
        <Mail kind="privacy" />.
      </p>

      <h2>What we store and why</h2>
      <ul>
        <li>
          <strong>Account data:</strong> your email address, a salted hash of
          your password (never the password itself) and your workspace name.
          Needed to provide your account (Art. 6(1)(b) GDPR). Your email address
          and a password are required to create an account; without them we
          cannot offer one. Everything else listed below is optional or follows
          from the features you switch on.
        </li>
        <li>
          <strong>Invitations:</strong> when someone invites you to a workspace,
          we store your email address, the role offered and who invited you
          until the invitation is used, revoked or has expired (7 days), and
          delete it a month after that. The invitation email is sent through our
          email provider. Needed to carry out the invitation (Art. 6(1)(b) and
          (f) GDPR).
        </li>
        <li>
          <strong>Scan data:</strong> the domains you add, the ownership
          verification status, scan results and PDF reports. A report is made
          the first time you download it and is kept, in our database and
          nowhere else, until its scan is deleted. Needed to provide the service
          (Art. 6(1)(b) GDPR). Scan results and their reports are deleted
          automatically after the history period of your plan (30 days on Free,
          90 on Professional, 365 on Agency).
        </li>
        <li>
          <strong>Audit log:</strong> a record of actions in your workspace:
          what happened, when, and which account did it (for example sign-in,
          scans started, members invited). It contains no IP addresses. Entries
          are deleted automatically after 12 months, or earlier when the
          workspace is deleted. Our legitimate interest in keeping the service
          secure and accountable (Art. 6(1)(f) GDPR).
        </li>
        <li>
          <strong>Feedback (optional):</strong> if you choose to rate
          SecureScope under Account, we store your star rating, the topic you
          pick and any comment you write, together with your account. It is read
          only by the operator, never published, and you can change or withdraw
          it at any time; it is also deleted with your account. Your consent
          (Art. 6(1)(a) GDPR), which you can withdraw whenever you like.
        </li>
        <li>
          <strong>Abuse protection:</strong> to limit abuse, such as repeated
          sign-in attempts, the server counts recent requests per IP address in
          its memory. These counters are not written to our database and
          disappear after a short time or when the server restarts. Our
          legitimate interest in keeping the service secure (Art. 6(1)(f) GDPR).
        </li>
        <li>
          <strong>Visit statistics:</strong> when you open a public page (the
          home page, sign-in, registration, password and email-confirmation
          pages, the sample report, the Agency features page and these legal
          pages) while signed out, we count the visit to learn whether the site
          is used. We store the page name, the website that linked to us (host
          name only), a coarse device type (desktop, mobile or tablet) and a
          one-way hash that changes every day. We do not store your IP address
          or browser details, set no cookie and keep nothing on your device, so
          we cannot recognise you on another day. We treat the hash as personal
          data, not as anonymous data. Your address is used briefly in memory to
          create the hash and to limit abuse. Visits are not counted while you
          are signed in, or if your browser sends Do Not Track or Global Privacy
          Control. These statistics are deleted after 90 days. Our legitimate
          interest in running and improving the service (Art. 6(1)(f) GDPR).
        </li>
        <li>
          <strong>Sign-in with Google or GitHub (optional):</strong> if you
          choose it, the provider tells us your verified email address and its
          own account ID for you. We store those two things so we can recognise
          you next time and link the sign-in to your account; we do not store
          your name or picture and receive no password. The provider learns that
          you signed in to SecureScope. Needed to provide your account (Art.
          6(1)(b) GDPR). If you do not use it, nothing is exchanged with these
          providers.
        </li>
        <li>
          <strong>Scheduled scans (optional):</strong> if you switch them on for
          a verified site, we store the schedule (daily or weekly, whether
          alerts are on, and when the next and last runs are or were). Each run
          is an ordinary scan and follows the same retention as any other scan.
          Needed to provide the feature you turned on (Art. 6(1)(b) GDPR).
        </li>
        <li>
          <strong>Emails:</strong> we send only service emails such as email
          confirmation and password reset and, if you switch on scheduled scans,
          an alert to the workspace owners, admins and security analysts when a
          scan reports a new finding (other than informational notes), the score
          drops by 5 points or more, or a scan fails. No marketing.
        </li>
        <li>
          <strong>Webhook addresses (optional):</strong> if you add one, we
          store the address you give us (it can contain a token, so it is not
          shown again in full) and when we last sent to it and what came back.
          On the same triggers as the alert email we send it the site&apos;s
          host name, the scan&apos;s score and link, and the titles of new
          findings. No evidence or page content is sent. If you choose Slack as
          the destination, the same facts are sent to Slack as a text message,
          and Slack&apos;s own terms and privacy policy apply to what it
          receives. Needed to provide the feature you turned on (Art. 6(1)(b)
          GDPR).
        </li>
        <li>
          <strong>API tokens and score badges (optional):</strong> if you create
          a CI token we store its name, a short prefix, a one-way digest of the
          token (never the token itself), who made it and when it was last used.
          If you switch on a badge for a verified site we store its random
          public address; anyone who has the address can see that site&apos;s
          latest score and grade, and nothing else. Needed to provide the
          features you turned on (Art. 6(1)(b) GDPR).
        </li>
        <li>
          <strong>Server logs:</strong> our hosting providers process technical
          data such as your IP address and the time of each request to deliver
          the site and protect it from abuse (Art. 6(1)(f) GDPR).
        </li>
      </ul>

      <h2>Cookies</h2>
      <p>
        Two cookies are set when you sign in: <code>ss_session</code> keeps you
        signed in, and <code>ss_csrf</code> protects your requests against
        forged cross-site requests. Both are strictly necessary, so no consent
        banner is needed. If you choose to sign in with Google or GitHub, a
        third cookie, <code>ss_oauth</code>, is set for ten minutes to complete
        that sign-in and is removed afterwards; it is equally strictly
        necessary. We use no advertising or tracking cookies. Our visit
        statistics use no cookies or other storage on your device.
      </p>
      <p>
        Your browser also keeps three small items so the app can do what you
        asked: your light or dark theme choice (local storage,{" "}
        <code>securescope-theme</code>, kept until you clear it), the workspace
        you selected (session storage, <code>securescope.org</code>, cleared
        when the tab closes) and, if you open an invitation link while signed
        out, the invitation token (session storage,{" "}
        <code>securescope.invite</code>, removed once it is used or the tab
        closes). They are used only for the feature you are using and are not
        used to track you.
      </p>

      <h2>Service providers</h2>
      <ul>
        <li>
          Cloudflare, Inc. &ndash; hosting of the website and request routing.
        </li>
        <li>
          Render Services, Inc. &ndash; hosting of the application server
          (United States, Oregon).
        </li>
        <li>Neon, Inc. &ndash; database hosting (Frankfurt, Germany).</li>
        <li>Brevo (Sendinblue SAS), France &ndash; sending service emails.</li>
      </ul>
      <p>
        Cloudflare, Render, Neon and Brevo process data on our behalf. Google
        Ireland Limited and GitHub, Inc. are not our processors: if you choose
        to sign in with them, they handle that sign-in under their own privacy
        policies. If you do not, nothing is exchanged with them.
      </p>
      <p>
        The application server runs in the USA, so account and scan data is
        processed there while you use the service; the database is in Frankfurt.
        Other providers may also process data in the USA. We rely on each
        provider&apos;s own transfer safeguards (EU-US Data Privacy Framework
        certification or standard contractual clauses); write to us if you want
        to know which one applies to which provider.
      </p>

      <h2>Your rights</h2>
      <p>
        You can ask for access, correction, deletion, restriction or export of
        your data (under <strong>Account</strong> you can download your account
        data as a file), and object to processing based on legitimate interest.
        To delete your account and its data, use <strong>Account</strong> in the
        app (it needs your password and takes effect at once), or email us. We
        keep account data until you delete the account or ask us to. Deleting
        removes your data from our database at once. Copies can remain for a
        limited time in the database provider&apos;s restore history and in our
        own backups until they are replaced, and in hosting logs under the
        providers&apos; own retention rules; we do not restore deleted accounts.
        You can also complain to a supervisory authority, for Berlin the
        Berliner Beauftragte für Datenschutz und Informationsfreiheit.
      </p>

      <h2>Automated decisions</h2>
      <p>
        We make no automated decisions that have legal or similarly significant
        effects on you. A scan&apos;s score is a heuristic summary of its checks
        and nothing more.
      </p>

      <h2>How scanning works</h2>
      <p>
        SecureScope sends ordinary read-only web requests to domains you have
        verified as yours. It does not scan domains whose ownership has not been
        verified. Ownership is shown with a DNS TXT record or a small file you
        publish under <code>/.well-known/</code>, and the proof expires after a
        set period, after which it must be repeated. For a main domain it also
        looks up that domain&apos;s public DNS records (SPF, DMARC, CAA and
        DNSSEC); no other domain is queried.
      </p>
    </Doc>
  );
}

function Terms() {
  return (
    <Doc page="terms" title="Terms of use">
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
        verification step. That step shows technical control only; it does not
        replace the permission of the owner if the domain is not yours. Using
        SecureScope against systems you are not authorized to test is forbidden
        and may be illegal.
      </p>
      <h2>3. Your account</h2>
      <p>
        Keep your password private and do not share your account. You are
        responsible for activity in your workspace. We may suspend or restrict
        an account that abuses the service, endangers its security or
        availability, or is used to scan sites without authorization; where
        possible we will tell you why first.
      </p>
      <h2>4. Development stage and no guarantees</h2>
      <p>
        SecureScope is still in development. The service is provided as is,
        without guarantee of availability or completeness of findings. Checks
        can miss issues or report false positives. Decisions based on the
        results are yours.
      </p>
      <h2>5. Liability</h2>
      <p>
        We are liable without limit for intent, gross negligence and injury to
        life, body or health, and as required by mandatory law. For slight
        negligence we are liable only for breach of essential contractual duties
        and only for foreseeable, typical damage.
      </p>
      <h2>6. Ending your use</h2>
      <p>
        You can stop using SecureScope at any time and delete your account
        yourself under Account (it needs your password and takes effect at
        once), or ask us to. If you are the only owner of a workspace that other
        people still use, hand over ownership first. We may end access for
        accounts that break these terms. Paid plans are not on sale yet; terms
        for payment, renewal and cancellation will be added here before any
        payment is taken.
      </p>
      <h2>7. Governing law</h2>
      <p>
        German law applies, except where mandatory consumer protection rules of
        your country of residence say otherwise.
      </p>
      <h2>8. Changes and contact</h2>
      <p>
        We may update these terms; the date above shows the latest version. If a
        change is material, we will announce it in the app or by email before it
        applies, and continued use does not replace any consent the law
        requires. Questions: <Mail kind="support" />.
      </p>
    </Doc>
  );
}

export default function LegalPage({ page }: { page: Page }) {
  if (page === "privacy") return <Privacy />;
  if (page === "terms") return <Terms />;
  return <Impressum />;
}
