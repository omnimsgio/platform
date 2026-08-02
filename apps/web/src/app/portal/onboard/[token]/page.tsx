"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import {
  clearPortalApiKey,
  ConnectWhatsApp,
  PORTAL_API_KEY_SESSION,
} from "../connect-whatsapp";

type AcceptOk = {
  invite_id: string;
  tenant_id: string;
  api_key_id: string;
  api_key: string;
  partner_name: string;
};

type Phase =
  | { kind: "loading" }
  | { kind: "show_key"; data: AcceptOk }
  | { kind: "connect"; apiKey: string; partnerName: string }
  | { kind: "already_accepted" }
  | { kind: "error"; message: string };

function flagEnabled(): boolean {
  const raw =
    process.env.FEATURE_EMBEDDED_SIGNUP ||
    process.env.NEXT_PUBLIC_FEATURE_EMBEDDED_SIGNUP ||
    "";
  return raw.trim().toLowerCase() === "true" || raw.trim() === "1";
}

export default function OnboardInvitePage() {
  const params = useParams<{ token: string }>();
  const token = useMemo(() => {
    const raw = params?.token;
    return typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : "";
  }, [params]);

  const apiBaseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.API_BASE_URL ||
    "https://api.omnimsg.io";
  const metaAppId =
    process.env.NEXT_PUBLIC_META_APP_ID ||
    process.env.META_APP_ID ||
    "3492919917530282";
  const esConfigId =
    process.env.NEXT_PUBLIC_META_ES_CONFIG_ID ||
    process.env.META_ES_CONFIG_ID ||
    "893783150448062";
  const esFeatureType = (
    process.env.WHATSAPP_ES_FEATURE_TYPE ||
    process.env.NEXT_PUBLIC_WHATSAPP_ES_FEATURE_TYPE ||
    ""
  ).trim();

  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [resumeKey, setResumeKey] = useState("");
  const esEnabled = flagEnabled();

  useEffect(() => {
    const clearOnLeave = () => {
      clearPortalApiKey();
    };
    window.addEventListener("pagehide", clearOnLeave);
    return () => {
      window.removeEventListener("pagehide", clearOnLeave);
    };
  }, []);

  useEffect(() => {
    if (!token) {
      setPhase({ kind: "error", message: "Missing invite token." });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(
          `${apiBaseUrl.replace(/\/$/, "")}/v1/partner-invites/accept`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token }),
          },
        );
        const payload = await response.json().catch(() => ({}));
        if (cancelled) return;
        if (response.status === 410) {
          const code = payload?.error?.code;
          if (code === "invite_already_accepted") {
            setPhase({ kind: "already_accepted" });
            return;
          }
          setPhase({
            kind: "error",
            message:
              payload?.error?.message ||
              "This invite is no longer available.",
          });
          return;
        }
        if (!response.ok) {
          setPhase({
            kind: "error",
            message:
              payload?.error?.message ||
              `Invite accept failed (${response.status})`,
          });
          return;
        }
        const data = payload as AcceptOk;
        try {
          sessionStorage.setItem(PORTAL_API_KEY_SESSION, data.api_key);
        } catch {
          /* ignore */
        }
        setPhase({ kind: "show_key", data });
      } catch (err) {
        if (!cancelled) {
          setPhase({
            kind: "error",
            message:
              err instanceof Error ? err.message : "Invite accept failed",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, token]);

  if (!esEnabled) {
    return (
      <main className="main rise">
        <p className="eyebrow">Onboarding</p>
        <h1>Embedded Signup disabled</h1>
        <p className="copy">
          FEATURE_EMBEDDED_SIGNUP is not enabled for this portal deployment.
        </p>
      </main>
    );
  }

  if (phase.kind === "loading") {
    return (
      <main className="main rise">
        <p className="eyebrow">Onboarding</p>
        <h1>Accepting invite…</h1>
      </main>
    );
  }

  if (phase.kind === "error") {
    return (
      <main className="main rise">
        <p className="eyebrow">Onboarding</p>
        <h1>Invite unavailable</h1>
        <p className="copy error" role="alert">
          {phase.message}
        </p>
      </main>
    );
  }

  if (phase.kind === "already_accepted") {
    return (
      <main className="main rise">
        <p className="eyebrow">Onboarding</p>
        <h1>Invite already accepted</h1>
        <p className="copy">
          This one-time link was already used. Continue with the API key from
          your earlier accept — no new invite is required while WhatsApp is
          still connecting (for example PHONE_PENDING).
        </p>
        <label className="field">
          <span>API key</span>
          <input
            type="password"
            autoComplete="off"
            value={resumeKey}
            onChange={(e) => setResumeKey(e.target.value)}
            placeholder="omni_…"
          />
        </label>
        <button
          type="button"
          className="cta"
          disabled={!resumeKey.trim().startsWith("omni_")}
          onClick={() => {
            const key = resumeKey.trim();
            try {
              sessionStorage.setItem(PORTAL_API_KEY_SESSION, key);
            } catch {
              /* ignore */
            }
            setPhase({
              kind: "connect",
              apiKey: key,
              partnerName: "Partner",
            });
          }}
        >
          Continue onboarding
        </button>
      </main>
    );
  }

  if (phase.kind === "show_key") {
    return (
      <main className="main rise">
        <p className="eyebrow">Onboarding</p>
        <h1>Welcome, {phase.data.partner_name}</h1>
        <p className="copy">
          Your workspace and first API key are ready. Copy the key now — it is
          shown only once — then continue to connect WhatsApp.
        </p>
        <p className="meta">
          Tenant <code>{phase.data.tenant_id}</code>
        </p>
        <label className="field">
          <span>API key (copy once)</span>
          <input type="text" readOnly value={phase.data.api_key} />
        </label>
        <button
          type="button"
          className="cta"
          onClick={() =>
            setPhase({
              kind: "connect",
              apiKey: phase.data.api_key,
              partnerName: phase.data.partner_name,
            })
          }
        >
          Continue to Connect WhatsApp
        </button>
      </main>
    );
  }

  return (
    <main className="main rise">
      <p className="eyebrow">Onboarding</p>
      <h1>{phase.partnerName}</h1>
      <p className="copy">
        Connect WhatsApp Business. After Embedded Signup, enter the 6-digit
        PIN; webhook and health checks run automatically until READY.
      </p>
      <ConnectWhatsApp
        metaAppId={metaAppId}
        esConfigId={esConfigId}
        apiBaseUrl={apiBaseUrl}
        esFeatureType={esFeatureType}
        initialApiKey={phase.apiKey}
        hideApiKeyInput
      />
    </main>
  );
}
