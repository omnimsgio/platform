import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "How FinestAR processes personal data for OmniMsg (omnimsg.io).",
  alternates: { canonical: "https://omnimsg.io/privacy" },
};

export default function PrivacyPage() {
  return (
    <div className="site">
      <div className="atmosphere glow" aria-hidden="true" />
      <main>
        <header className="doc-header">
          <p className="eyebrow">
            <Link href="/">omnimsg.io</Link>
          </p>
          <h1>Privacy Policy</h1>
          <p className="meta">
            Last updated: 21 July 2026 · Controller: FinestAR d.o.o. (OmniMsg)
          </p>
        </header>

        <div className="doc">
          <p>
            This Privacy Policy describes how{" "}
            <strong>FinestAR d.o.o.</strong> (“FinestAR”, “we”, “us”), operating
            the <strong>OmniMsg</strong> platform at{" "}
            <a href="https://omnimsg.io">omnimsg.io</a>, processes personal data
            when you use our website, portal, APIs, or related services. It is
            written for Meta App Review and GDPR-oriented transparency for users
            in Croatia and the wider EU/EEA. It is a starter policy; legal counsel
            should review it before heavy production use.
          </p>

          <h2>1. Who we are</h2>
          <p>
            OmniMsg is an API-first omnichannel messaging platform built by
            FinestAR. For privacy matters we act as{" "}
            <strong>data controller</strong> for account, billing, and platform
            administration data. When we process message-related data on behalf
            of a business customer, we typically act as a{" "}
            <strong>processor</strong> under that customer’s instructions.
          </p>
          <p>
            Contact:{" "}
            <a href="mailto:hello@finestar.hr">hello@finestar.hr</a>
            <br />
            Website:{" "}
            <a href="https://finestar.hr/" rel="noopener noreferrer">
              finestar.hr
            </a>
          </p>

          <h2>2. Data we collect</h2>
          <h3>Account and onboarding</h3>
          <p>
            When you request access or create a tenant, we may process name,
            business name, email, phone, role, and related contact details. For
            WhatsApp Business Account (WABA) onboarding (including Meta Embedded
            Signup flows), we may receive business identifiers, WABA and phone
            number IDs, Meta Business Manager linkage, and token or credential
            metadata needed to connect your account to OmniMsg.
          </p>
          <h3>API keys and authentication</h3>
          <p>
            We store hashed or encrypted API credentials, session tokens, and
            access logs (timestamps, IP addresses, user agents, and request
            metadata) to secure the service and investigate abuse.
          </p>
          <h3>Message and delivery metadata</h3>
          <p>
            OmniMsg processes and may store message metadata such as message
            IDs, channel, direction, status, timestamps, recipient identifiers
            (for example phone numbers), template names, and provider delivery
            receipts. Message body content may be processed for delivery and
            temporarily retained as needed for retries, debugging, or
            compliance with provider requirements. We do{" "}
            <strong>not</strong> claim end-to-end encryption of message content
            within OmniMsg, and we do not retain plaintext message bodies beyond
            what is required for operation, support, and legal obligations.
          </p>
          <h3>Webhooks</h3>
          <p>
            Inbound webhooks from Meta/WhatsApp and other providers may include
            delivery events, status updates, and related payloads. We store and
            process these payloads to update delivery state, drive customer
            callbacks, and operate the platform.
          </p>
          <h3>Website usage</h3>
          <p>
            Our marketing site is primarily informational. Server logs may
            include IP address, requested URL, and user agent for security and
            reliability. We do not use advertising trackers on the marketing
            site as of the date above.
          </p>

          <h2>3. Why we process data</h2>
          <ul>
            <li>Provide, secure, and improve OmniMsg</li>
            <li>Onboard businesses to WhatsApp and other channels</li>
            <li>Authenticate API and portal access</li>
            <li>Route messages and report delivery status</li>
            <li>Invoice usage and communicate about the service</li>
            <li>Comply with law and respond to lawful requests</li>
          </ul>
          <p>
            Legal bases under GDPR include performance of a contract, legitimate
            interests (security, product improvement, B2B communications), and
            legal obligation where applicable. Where consent is required (for
            example certain marketing), we will ask separately.
          </p>

          <h2>4. Subprocessors and sharing</h2>
          <p>We share data only as needed to run the service, including with:</p>
          <ul>
            <li>
              <strong>Meta Platforms / WhatsApp Cloud API</strong> — messaging,
              webhooks, and WABA onboarding
            </li>
            <li>
              <strong>Hosting and infrastructure providers</strong> — servers,
              databases, logs, and backups for OmniMsg deployments
            </li>
            <li>
              Professional advisors or authorities when legally required
            </li>
          </ul>
          <p>
            We do not sell personal data. Business customers remain responsible
            for their own lawful basis toward end users of messaging (for
            example WhatsApp recipients).
          </p>

          <h2>5. International transfers</h2>
          <p>
            Some subprocessors (notably Meta) may process data outside the
            EU/EEA. Where transfers occur, we rely on appropriate safeguards such
            as adequacy decisions or Standard Contractual Clauses, as applicable
            to that provider.
          </p>

          <h2>6. Retention</h2>
          <p>
            Account and billing records are kept for the life of the customer
            relationship and for statutory periods afterward. Message metadata
            and webhook payloads are retained for operational windows needed for
            delivery, support, and auditing, then deleted or anonymized.
            Retention may be configurable within platform bounds for enterprise
            customers. API keys remain until rotated or revoked.
          </p>

          <h2>7. Security</h2>
          <p>
            We apply technical and organizational measures appropriate to a
            multi-tenant messaging platform, including tenant isolation,
            credential hashing/encryption, access controls, and transport
            encryption (TLS). No method of transmission or storage is fully
            secure; please contact us promptly if you suspect unauthorized
            access.
          </p>

          <h2>8. Your rights (GDPR)</h2>
          <p>
            If you are in the EU/EEA (including Croatia), you may have the right
            to access, rectify, erase, restrict, or port your personal data, and
            to object to certain processing. You may also lodge a complaint with
            your supervisory authority (in Croatia: AZOP — Agencija za zaštitu
            osobnih podataka). To exercise rights, email{" "}
            <a href="mailto:hello@finestar.hr">hello@finestar.hr</a>. We may
            need to verify your identity and, where we act as processor, redirect
            requests to the relevant business customer.
          </p>

          <h2>9. Children</h2>
          <p>
            OmniMsg is a B2B service and is not directed at children under 16. We
            do not knowingly collect personal data from children.
          </p>

          <h2>10. Changes</h2>
          <p>
            We may update this policy from time to time. The “Last updated” date
            at the top will change when we do. Material changes affecting
            customers will be communicated through reasonable channels (for
            example email or product notice).
          </p>

          <h2>11. Contact</h2>
          <p>
            Privacy questions:{" "}
            <a href="mailto:hello@finestar.hr">hello@finestar.hr</a>
          </p>
        </div>
      </main>

      <footer className="footer">
        <Link href="/" className="footer-brand">
          <Image
            src="/brand/omnimsg-icon.png"
            alt=""
            width={36}
            height={36}
          />
          <span>omnimsg.io</span>
        </Link>
        <nav className="footer-nav" aria-label="Legal">
          <Link href="/privacy">Privacy</Link>
        </nav>
        <p>
          Built by{" "}
          <a href="https://finestar.hr/" rel="noopener noreferrer">
            FinestAR
          </a>
        </p>
      </footer>

      <style>{`
        .site {
          position: relative;
          min-height: 100vh;
          overflow-x: clip;
          background:
            radial-gradient(120% 80% at 10% -10%, rgba(0, 194, 203, 0.22), transparent 55%),
            radial-gradient(90% 70% at 100% 0%, rgba(0, 71, 171, 0.28), transparent 50%),
            linear-gradient(180deg, #e8f4f8 0%, #f7fbfd 42%, #ffffff 100%);
        }

        .glow {
          position: absolute;
          inset: -10% -5% auto;
          height: min(48vh, 420px);
          background:
            radial-gradient(ellipse at 35% 40%, rgba(0, 194, 203, 0.18), transparent 55%),
            radial-gradient(ellipse at 70% 30%, rgba(0, 71, 171, 0.2), transparent 50%);
          pointer-events: none;
          z-index: 0;
        }

        main,
        .footer {
          position: relative;
          z-index: 1;
          width: min(720px, calc(100% - 2.5rem));
          margin-inline: auto;
        }

        .doc-header {
          padding: 3.5rem 0 1.5rem;
        }

        .eyebrow {
          margin: 0 0 0.75rem;
          font-family: var(--font-display);
          font-weight: 600;
          font-size: 0.95rem;
        }

        .eyebrow a {
          color: var(--brand-blue);
        }

        .eyebrow a:hover {
          color: var(--brand-teal);
        }

        .doc-header h1 {
          margin: 0 0 0.65rem;
          font-family: var(--font-display);
          font-size: clamp(1.75rem, 4vw, 2.25rem);
          letter-spacing: -0.03em;
          color: var(--brand-navy);
        }

        .meta {
          margin: 0;
          font-size: 0.95rem;
          color: var(--brand-muted);
        }

        .doc {
          padding-bottom: 1rem;
          font-size: 1.02rem;
          line-height: 1.65;
          color: var(--brand-muted);
        }

        .doc h2 {
          margin: 2.25rem 0 0.75rem;
          font-family: var(--font-display);
          font-size: 1.25rem;
          letter-spacing: -0.02em;
          color: var(--brand-navy);
        }

        .doc h3 {
          margin: 1.35rem 0 0.5rem;
          font-family: var(--font-display);
          font-size: 1.05rem;
          color: var(--brand-navy);
        }

        .doc p {
          margin: 0 0 1rem;
        }

        .doc ul {
          margin: 0 0 1rem;
          padding-left: 1.25rem;
        }

        .doc li {
          margin-bottom: 0.4rem;
        }

        .doc a {
          color: var(--brand-blue);
        }

        .doc a:hover {
          color: var(--brand-teal);
        }

        .doc strong {
          color: var(--brand-navy);
          font-weight: 600;
        }

        .footer {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
          padding: 3.5rem 0 2.5rem;
          margin-top: 2rem;
          border-top: 1px solid rgba(10, 17, 40, 0.08);
          color: var(--brand-muted);
          font-size: 0.95rem;
        }

        .footer-brand {
          display: inline-flex;
          align-items: center;
          gap: 0.65rem;
          font-family: var(--font-display);
          font-weight: 600;
          color: var(--brand-navy);
        }

        .footer-nav a {
          color: var(--brand-blue);
        }

        .footer-nav a:hover {
          color: var(--brand-teal);
        }

        .footer a[href^="https://finestar"] {
          color: var(--brand-blue);
        }

        .footer a[href^="https://finestar"]:hover {
          color: var(--brand-teal);
        }

        @media (max-width: 540px) {
          .footer {
            flex-direction: column;
            align-items: flex-start;
          }
        }
      `}</style>
    </div>
  );
}
