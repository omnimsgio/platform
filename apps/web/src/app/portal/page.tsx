import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ConnectWhatsApp } from "./connect-whatsapp";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Portal",
  description: "OmniMsg customer portal — Connect WhatsApp.",
  robots: { index: false, follow: false },
  alternates: { canonical: "https://app.omnimsg.io" },
};

function flagEnabled(): boolean {
  const raw =
    process.env.FEATURE_EMBEDDED_SIGNUP ||
    process.env.NEXT_PUBLIC_FEATURE_EMBEDDED_SIGNUP ||
    "";
  return raw.trim().toLowerCase() === "true" || raw.trim() === "1";
}

function esFeatureTypeFromEnv(): string {
  return (
    process.env.WHATSAPP_ES_FEATURE_TYPE ||
    process.env.NEXT_PUBLIC_WHATSAPP_ES_FEATURE_TYPE ||
    ""
  ).trim();
}

export default function PortalPage() {
  const esEnabled = flagEnabled();
  const metaAppId =
    process.env.NEXT_PUBLIC_META_APP_ID ||
    process.env.META_APP_ID ||
    "3492919917530282";
  const esConfigId =
    process.env.NEXT_PUBLIC_META_ES_CONFIG_ID ||
    process.env.META_ES_CONFIG_ID ||
    "893783150448062";
  const apiBaseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.API_BASE_URL ||
    "https://api.omnimsg.io";
  const esFeatureType = esFeatureTypeFromEnv();

  return (
    <div className="shell">
      <header className="bar">
        <Link href="https://omnimsg.io" className="brand">
          <Image
            src="/brand/omnimsg-icon.png"
            alt=""
            width={32}
            height={32}
            priority
          />
          <span>omnimsg.io</span>
        </Link>
        <button type="button" className="signin" disabled title="Coming soon">
          Sign in
        </button>
      </header>

      <main className="main rise">
        <p className="eyebrow">Portal</p>
        <h1>Workspace</h1>
        <p className="copy">
          Messaging API traffic runs on{" "}
          <a href="https://api.omnimsg.io/health">api.omnimsg.io</a>. Sign-in
          ships later; Embedded Signup uses a tenant API key for now.
        </p>

        {esEnabled ? (
          <ConnectWhatsApp
            metaAppId={metaAppId}
            esConfigId={esConfigId}
            apiBaseUrl={apiBaseUrl}
            esFeatureType={esFeatureType}
          />
        ) : (
          <p className="hint">
            Connect WhatsApp is disabled. Set{" "}
            <code>FEATURE_EMBEDDED_SIGNUP=true</code> on the web service to
            enable.
          </p>
        )}
      </main>

      <style>{`
        .shell {
          min-height: 100vh;
          background:
            linear-gradient(180deg, #f0f7fa 0%, #ffffff 55%);
          color: var(--brand-navy);
        }

        .bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
          padding: 1rem 1.5rem;
          border-bottom: 1px solid rgba(10, 17, 40, 0.08);
          background: rgba(255, 255, 255, 0.85);
          backdrop-filter: blur(8px);
        }

        .brand {
          display: inline-flex;
          align-items: center;
          gap: 0.65rem;
          font-family: var(--font-display);
          font-weight: 600;
          font-size: 0.95rem;
        }

        .signin {
          font-family: var(--font-body);
          font-size: 0.9rem;
          padding: 0.45rem 0.95rem;
          border-radius: 6px;
          border: 1px solid rgba(10, 17, 40, 0.15);
          background: #eef2f5;
          color: var(--brand-muted);
          opacity: 0.75;
        }

        .main {
          width: min(520px, calc(100% - 2.5rem));
          margin: 0 auto;
          padding: 4.5rem 0 3rem;
        }

        .eyebrow {
          margin: 0 0 0.5rem;
          font-size: 0.8rem;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--brand-teal);
          font-weight: 600;
        }

        h1 {
          margin: 0 0 1rem;
          font-family: var(--font-display);
          font-size: clamp(1.75rem, 4vw, 2.25rem);
          letter-spacing: -0.03em;
        }

        h2 {
          margin: 0 0 0.75rem;
          font-family: var(--font-display);
          font-size: 1.25rem;
          letter-spacing: -0.02em;
        }

        .copy {
          margin: 0 0 1.25rem;
          font-size: 1.05rem;
          line-height: 1.55;
          color: var(--brand-muted);
        }

        .copy a {
          color: var(--brand-blue);
          border-bottom: 1px solid rgba(0, 71, 171, 0.35);
        }

        .hint {
          margin: 0;
          font-size: 0.9rem;
          color: var(--brand-muted);
        }

        .hint code,
        .meta code,
        .copy code {
          font-size: 0.85em;
        }

        .panel {
          margin-top: 2rem;
          padding: 1.35rem 0 0;
          border-top: 1px solid rgba(10, 17, 40, 0.08);
        }

        .panel.success .eyebrow {
          color: var(--brand-teal);
        }

        .field {
          display: grid;
          gap: 0.35rem;
          margin-bottom: 1rem;
          font-size: 0.85rem;
          color: var(--brand-muted);
        }

        .field input {
          font-family: var(--font-body);
          font-size: 0.95rem;
          padding: 0.65rem 0.75rem;
          border-radius: 6px;
          border: 1px solid rgba(10, 17, 40, 0.18);
          background: #fff;
          color: var(--brand-navy);
        }

        .cta {
          font-family: var(--font-body);
          font-size: 0.95rem;
          font-weight: 600;
          padding: 0.65rem 1.1rem;
          border-radius: 6px;
          border: none;
          background: var(--brand-blue);
          color: #fff;
          cursor: pointer;
        }

        .cta:disabled {
          opacity: 0.55;
          cursor: not-allowed;
        }

        .error {
          margin: 0.9rem 0 0;
          font-size: 0.9rem;
          color: #9b1c1c;
        }

        .meta {
          margin: 0;
          font-size: 0.85rem;
          line-height: 1.5;
          color: var(--brand-muted);
        }
      `}</style>
    </div>
  );
}
