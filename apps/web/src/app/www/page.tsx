import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

export const metadata: Metadata = {
  title: {
    absolute: "OmniMsg — One platform. Every message.",
  },
  alternates: { canonical: "https://omnimsg.io" },
};

export default function MarketingPage() {
  return (
    <div className="site">
      <div className="atmosphere glow" aria-hidden="true" />
      <main>
        <section className="hero" aria-label="OmniMsg">
          <Image
            className="lockup rise"
            src="/brand/omnimsg-lockup.png"
            alt="omnimsg.io — One platform. Every message."
            width={560}
            height={560}
            priority
          />
          <p className="line rise rise-delay-1">
            One API. Any channel. Any provider.
          </p>
          <p className="support rise rise-delay-2">
            API-first omnichannel messaging for businesses — WhatsApp via Meta
            Cloud API on a Solution Partner path, with more channels behind the
            same stable interface.
          </p>
          <div className="ctas rise rise-delay-3">
            <a
              className="cta-primary"
              href="mailto:hello@finestar.hr?subject=OmniMsg%20access"
            >
              Request access
            </a>
            <a className="cta-secondary" href="https://api.omnimsg.io/health">
              API
            </a>
          </div>
        </section>

        <section className="section" aria-labelledby="why-heading">
          <h2 id="why-heading">Integrate once. Route anywhere.</h2>
          <p>
            Customers call one HTTP API. OmniMsg handles auth, delivery, and
            provider adapters so vendor changes stay off your critical path.
          </p>
        </section>

        <section className="section" aria-labelledby="channels-heading">
          <h2 id="channels-heading">Channels</h2>
          <ul className="channels">
            <li>WhatsApp Business (Meta Cloud API) — live path</li>
            <li>SMS</li>
            <li>Email</li>
            <li>RCS</li>
            <li>Push</li>
          </ul>
        </section>
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
          height: min(72vh, 720px);
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

        .hero {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
          justify-content: center;
          align-items: center;
          text-align: center;
          padding: 3rem 0 4rem;
          gap: 1.1rem;
        }

        .lockup {
          width: min(420px, 78vw);
          height: auto;
          filter: drop-shadow(0 18px 40px rgba(10, 17, 40, 0.12));
        }

        .line {
          margin: 0;
          font-family: var(--font-display);
          font-size: clamp(1.15rem, 2.4vw, 1.55rem);
          font-weight: 600;
          letter-spacing: -0.02em;
          color: var(--brand-navy);
        }

        .support {
          margin: 0;
          max-width: 34rem;
          font-size: 1.05rem;
          line-height: 1.55;
          color: var(--brand-muted);
        }

        .ctas {
          display: flex;
          flex-wrap: wrap;
          gap: 1.25rem 1.75rem;
          justify-content: center;
          align-items: baseline;
          margin-top: 0.75rem;
        }

        .cta-primary {
          font-family: var(--font-display);
          font-weight: 600;
          font-size: 1.05rem;
          color: var(--brand-navy);
        }

        .cta-secondary {
          font-size: 0.95rem;
          color: var(--brand-blue);
          border-bottom: 1px solid transparent;
          transition: border-color 0.2s ease, color 0.2s ease;
        }

        .cta-secondary:hover {
          color: var(--brand-teal);
          border-bottom-color: var(--brand-teal);
        }

        .section {
          padding: 4.5rem 0 1rem;
        }

        .section h2 {
          margin: 0 0 0.85rem;
          font-family: var(--font-display);
          font-size: clamp(1.4rem, 3vw, 1.85rem);
          letter-spacing: -0.03em;
        }

        .section p {
          margin: 0;
          font-size: 1.05rem;
          line-height: 1.6;
          color: var(--brand-muted);
          max-width: 38rem;
        }

        .channels {
          margin: 0;
          padding: 0;
          list-style: none;
          display: grid;
          gap: 0.65rem;
          font-size: 1.05rem;
          color: var(--brand-navy);
        }

        .channels li {
          padding-left: 1rem;
          border-left: 3px solid var(--brand-teal);
        }

        .footer {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
          padding: 3.5rem 0 2.5rem;
          margin-top: 3rem;
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
