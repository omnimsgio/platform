"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type ConnectionState = {
  status: string;
  statusReason: string | null;
  updatedAt: string | null;
  message: string;
  badge: string;
  phoneNumberId: string | null;
  wabaId: string | null;
  correlationId: string | null;
  lastError: string | null;
  recoveryTarget: string | null;
};

type SessionInfo = {
  phone_number_id?: string;
  waba_id?: string;
  business_id?: string;
};

type Props = {
  metaAppId: string;
  esConfigId: string;
  apiBaseUrl: string;
  /** Meta ES extras.featureType; empty = classic exclusive Cloud API onboarding. */
  esFeatureType: string;
  /** Prefill from invite accept; also written to sessionStorage. */
  initialApiKey?: string;
  /** Hide paste-key field (invite / resume with known key). */
  hideApiKeyInput?: boolean;
};

export const PORTAL_API_KEY_SESSION = "omnimsg_portal_api_key";

export function clearPortalApiKey(): void {
  try {
    sessionStorage.removeItem(PORTAL_API_KEY_SESSION);
  } catch {
    /* ignore */
  }
}

const FINISH_EVENTS = new Set([
  "FINISH",
  "FINISH_ONLY_WABA",
  "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING",
]);

function maskId(value: string | null | undefined): string {
  if (!value) return "(missing)";
  if (value.length <= 4) return "***";
  return `***${value.slice(-4)}`;
}

function newEsAttemptId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `es_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

function esLog(
  attemptId: string,
  message: string,
  detail?: Record<string, unknown>,
): void {
  if (detail) {
    console.info(`[omnimsg:es][attempt=${attemptId}] ${message}`, detail);
  } else {
    console.info(`[omnimsg:es][attempt=${attemptId}] ${message}`);
  }
}

function esWarn(
  attemptId: string,
  message: string,
  detail?: Record<string, unknown>,
): void {
  if (detail) {
    console.warn(`[omnimsg:es][attempt=${attemptId}] ${message}`, detail);
  } else {
    console.warn(`[omnimsg:es][attempt=${attemptId}] ${message}`);
  }
}

function elapsedSeconds(startedAt: number): string {
  return `${((performance.now() - startedAt) / 1000).toFixed(1)} s`;
}

declare global {
  interface Window {
    FB?: {
      init: (params: Record<string, unknown>) => void;
      login: (
        callback: (response: {
          authResponse?: { code?: string };
          status?: string;
        }) => void,
        options: Record<string, unknown>,
      ) => void;
    };
    fbAsyncInit?: () => void;
  }
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Meta SDK"));
    document.body.appendChild(script);
  });
}

function formatRelative(iso: string | null): string | null {
  if (!iso) return null;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return `prije ${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `prije ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `prije ${hours} h`;
  const days = Math.round(hours / 24);
  return `prije ${days} d`;
}

function mapConnection(payload: Record<string, unknown>): ConnectionState {
  return {
    status: String(payload.status || "NOT_CONNECTED"),
    statusReason:
      typeof payload.status_reason === "string" ? payload.status_reason : null,
    updatedAt:
      typeof payload.updated_at === "string" ? payload.updated_at : null,
    message: String(payload.message || ""),
    badge: String(payload.badge || "neutral"),
    phoneNumberId:
      typeof payload.phone_number_id === "string"
        ? payload.phone_number_id
        : null,
    wabaId: typeof payload.waba_id === "string" ? payload.waba_id : null,
    correlationId:
      typeof payload.correlation_id === "string"
        ? payload.correlation_id
        : null,
    lastError:
      typeof payload.last_error === "string" ? payload.last_error : null,
    recoveryTarget:
      typeof payload.recovery_target === "string"
        ? payload.recovery_target
        : null,
  };
}

export function ConnectWhatsApp({
  metaAppId,
  esConfigId,
  apiBaseUrl,
  esFeatureType,
  initialApiKey,
  hideApiKeyInput = false,
}: Props) {
  const [apiKey, setApiKey] = useState(initialApiKey?.trim() || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConnectionState | null>(null);
  const [sdkReady, setSdkReady] = useState(false);
  const [pin, setPin] = useState("");
  const sessionRef = useRef<SessionInfo | null>(null);
  const attemptIdRef = useRef<string | null>(null);
  const attemptStartedAtRef = useRef<number | null>(null);
  const lastFinishEventRef = useRef<string | null>(null);
  const esStateRef = useRef<string | null>(null);
  const autoStepRef = useRef<string | null>(null);
  const coexistenceMode =
    esFeatureType.trim() === "whatsapp_business_app_onboarding";

  useEffect(() => {
    if (initialApiKey?.trim()) {
      try {
        sessionStorage.setItem(PORTAL_API_KEY_SESSION, initialApiKey.trim());
      } catch {
        /* ignore */
      }
      setApiKey(initialApiKey.trim());
      return;
    }
    try {
      const stored = sessionStorage.getItem(PORTAL_API_KEY_SESSION);
      if (stored) setApiKey(stored);
    } catch {
      /* ignore */
    }
  }, [initialApiKey]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (
        event.origin !== "https://www.facebook.com" &&
        event.origin !== "https://web.facebook.com"
      ) {
        return;
      }
      try {
        const data =
          typeof event.data === "string" ? JSON.parse(event.data) : event.data;
        if (data?.type !== "WA_EMBEDDED_SIGNUP") return;
        const attemptId = attemptIdRef.current || "unknown";
        if (typeof data.event === "string") {
          esLog(attemptId, `event received (${data.event})`);
        }
        if (FINISH_EVENTS.has(data.event)) {
          lastFinishEventRef.current = String(data.event);
          const info = (data.data || {}) as SessionInfo;
          sessionRef.current = {
            phone_number_id: info.phone_number_id,
            waba_id: info.waba_id,
            business_id: info.business_id,
          };
          esLog(attemptId, "session stored", {
            event: data.event,
            business_id: maskId(info.business_id),
            waba_id: maskId(info.waba_id),
            phone_number_id: maskId(info.phone_number_id),
          });
        }
      } catch {
        /* ignore non-JSON */
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        window.fbAsyncInit = () => {
          window.FB?.init({
            appId: metaAppId,
            autoLogAppEvents: true,
            xfbml: true,
            version: "v21.0",
          });
          if (!cancelled) setSdkReady(true);
        };
        await loadScript("https://connect.facebook.net/en_US/sdk.js");
        if (window.FB && !cancelled) {
          window.FB.init({
            appId: metaAppId,
            autoLogAppEvents: true,
            xfbml: true,
            version: "v21.0",
          });
          setSdkReady(true);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Meta SDK failed to load");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [metaAppId]);

  const authHeaders = useCallback((): HeadersInit => {
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey.trim()}`,
    };
  }, [apiKey]);

  const refreshConnection = useCallback(async (): Promise<ConnectionState | null> => {
    if (!apiKey.trim()) {
      setConnection(null);
      return null;
    }
    const response = await fetch(
      `${apiBaseUrl.replace(/\/$/, "")}/v1/whatsapp/connection`,
      { headers: authHeaders() },
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      return null;
    }
    const mapped = mapConnection(payload as Record<string, unknown>);
    setConnection(mapped);
    return mapped;
  }, [apiBaseUrl, apiKey, authHeaders]);

  useEffect(() => {
    void refreshConnection();
  }, [refreshConnection]);

  const persistKey = useCallback((value: string) => {
    setApiKey(value);
    try {
      if (value) sessionStorage.setItem(PORTAL_API_KEY_SESSION, value);
      else sessionStorage.removeItem(PORTAL_API_KEY_SESSION);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (connection?.status === "READY") {
      clearPortalApiKey();
    }
  }, [connection?.status]);

  const completeAttach = useCallback(
    async (code: string, session: SessionInfo, attemptId: string) => {
      const phoneNumberId = session.phone_number_id;
      const wabaId = session.waba_id;
      const businessId = session.business_id;
      const finishEvent = lastFinishEventRef.current;
      const requireBusiness =
        coexistenceMode ||
        finishEvent === "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING";

      if (!phoneNumberId || !wabaId || (requireBusiness && !businessId)) {
        esWarn(attemptId, "session validation failed — skip completeAttach", {
          event: finishEvent,
          business_id: maskId(businessId),
          waba_id: maskId(wabaId),
          phone_number_id: maskId(phoneNumberId),
        });
        throw new Error(
          requireBusiness
            ? "Embedded Signup finished without business_id / waba_id / phone_number_id — retry Connect"
            : "Embedded Signup finished without phone_number_id / waba_id — retry Connect",
        );
      }

      esLog(attemptId, "completeAttach request", {
        business_id: maskId(businessId),
        waba_id: maskId(wabaId),
        phone_number_id: maskId(phoneNumberId),
      });
      const response = await fetch(
        `${apiBaseUrl.replace(/\/$/, "")}/v1/whatsapp/embedded-signup/complete`,
        {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({
            code,
            waba_id: wabaId,
            phone_number_id: phoneNumberId,
            meta_business_id: businessId || undefined,
            state: esStateRef.current || undefined,
          }),
        },
      );
      const payload = await response.json().catch(() => ({}));
      esLog(attemptId, `completeAttach response (${response.status})`);
      if (!response.ok) {
        const message =
          payload?.error?.message ||
          `Attach failed (${response.status})`;
        const correlation = payload?.error?.correlation_id;
        throw new Error(
          correlation ? `${message} (${correlation})` : message,
        );
      }
      const next = await refreshConnection();
      esLog(attemptId, "portal status update", {
        status: next?.status || "(unknown)",
      });
    },
    [apiBaseUrl, authHeaders, coexistenceMode, refreshConnection],
  );

  const launch = useCallback(() => {
    setError(null);
    if (!apiKey.trim()) {
      setError("Paste your tenant API key first (interim portal auth).");
      return;
    }
    if (!window.FB || !sdkReady) {
      setError("Meta SDK is not ready yet. Try again in a moment.");
      return;
    }
    const attemptId = newEsAttemptId();
    const startedAt = performance.now();
    attemptIdRef.current = attemptId;
    attemptStartedAtRef.current = startedAt;
    lastFinishEventRef.current = null;
    setBusy(true);
    sessionRef.current = null;
    esLog(attemptId, "ES started", {
      featureType: esFeatureType || "(classic)",
    });
    void (async () => {
      try {
        const startRes = await fetch(
          `${apiBaseUrl.replace(/\/$/, "")}/v1/whatsapp/embedded-signup/start`,
          { method: "POST", headers: authHeaders() },
        );
        const startPayload = await startRes.json().catch(() => ({}));
        if (!startRes.ok) {
          const message =
            startPayload?.error?.message ||
            `Start failed (${startRes.status})`;
          throw new Error(message);
        }
        esStateRef.current =
          typeof startPayload?.state === "string" ? startPayload.state : null;
        await refreshConnection();

        window.FB!.login(
          (response) => {
            void (async () => {
              try {
                const code = response.authResponse?.code;
                if (!code) {
                  throw new Error("Embedded Signup did not return an auth code");
                }
                await new Promise((r) => setTimeout(r, 400));
                const session = sessionRef.current;
                if (!session) {
                  throw new Error(
                    "Missing Embedded Signup session — retry Connect",
                  );
                }
                await completeAttach(code, session, attemptId);
                esLog(attemptId, `completed in ${elapsedSeconds(startedAt)}`);
              } catch (err) {
                esWarn(attemptId, `ERROR after ${elapsedSeconds(startedAt)}`, {
                  message: err instanceof Error ? err.message : String(err),
                });
                setError(err instanceof Error ? err.message : "Connect failed");
              } finally {
                setBusy(false);
              }
            })();
          },
          {
            config_id: esConfigId,
            response_type: "code",
            override_default_response_type: true,
            extras: {
              setup: {},
              featureType: esFeatureType,
              sessionInfoVersion: "3",
            },
          },
        );
      } catch (err) {
        esWarn(attemptId, `ERROR after ${elapsedSeconds(startedAt)}`, {
          message: err instanceof Error ? err.message : String(err),
        });
        setBusy(false);
        setError(err instanceof Error ? err.message : "Connect failed");
      }
    })();
  }, [
    apiBaseUrl,
    apiKey,
    authHeaders,
    completeAttach,
    esConfigId,
    esFeatureType,
    refreshConnection,
    sdkReady,
  ]);

  const relative = formatRelative(connection?.updatedAt ?? null);

  const submitWebhook = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const response = await fetch(
        `${apiBaseUrl.replace(/\/$/, "")}/v1/whatsapp/provision-webhook`,
        { method: "POST", headers: authHeaders() },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message =
          payload?.error?.message ||
          `Webhook provision failed (${response.status})`;
        const correlation = payload?.error?.correlation_id;
        throw new Error(correlation ? `${message} (${correlation})` : message);
      }
      await refreshConnection();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Webhook provision failed");
    } finally {
      setBusy(false);
    }
  }, [apiBaseUrl, authHeaders, refreshConnection]);

  const submitHealth = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const response = await fetch(
        `${apiBaseUrl.replace(/\/$/, "")}/v1/whatsapp/health-check`,
        { method: "POST", headers: authHeaders() },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message =
          payload?.error?.message || `Health check failed (${response.status})`;
        const correlation = payload?.error?.correlation_id;
        throw new Error(correlation ? `${message} (${correlation})` : message);
      }
      const next = await refreshConnection();
      if (next?.status === "READY") {
        clearPortalApiKey();
      }
      if (payload?.checks) {
        const failed = Object.entries(payload.checks as Record<string, boolean>)
          .filter(([, ok]) => !ok)
          .map(([key]) => key);
        if (failed.length && payload.status !== "READY") {
          setError(`Health failed: ${failed.join(", ")}`);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Health check failed");
    } finally {
      setBusy(false);
    }
  }, [apiBaseUrl, authHeaders, refreshConnection]);

  const submitPin = useCallback(async () => {
    setError(null);
    if (!/^\d{6}$/.test(pin.trim())) {
      setError("PIN must be exactly 6 digits.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(
        `${apiBaseUrl.replace(/\/$/, "")}/v1/whatsapp/register-phone`,
        {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({ pin: pin.trim() }),
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message =
          payload?.error?.message || `Register failed (${response.status})`;
        const correlation = payload?.error?.correlation_id;
        throw new Error(correlation ? `${message} (${correlation})` : message);
      }
      setPin("");
      // Auto-chain: webhook → health (PIN is the only required human step).
      const webhookRes = await fetch(
        `${apiBaseUrl.replace(/\/$/, "")}/v1/whatsapp/provision-webhook`,
        { method: "POST", headers: authHeaders() },
      );
      const webhookPayload = await webhookRes.json().catch(() => ({}));
      if (!webhookRes.ok) {
        const message =
          webhookPayload?.error?.message ||
          `Webhook provision failed (${webhookRes.status})`;
        throw new Error(message);
      }
      const healthRes = await fetch(
        `${apiBaseUrl.replace(/\/$/, "")}/v1/whatsapp/health-check`,
        { method: "POST", headers: authHeaders() },
      );
      const healthPayload = await healthRes.json().catch(() => ({}));
      if (!healthRes.ok) {
        const message =
          healthPayload?.error?.message ||
          `Health check failed (${healthRes.status})`;
        throw new Error(message);
      }
      const next = await refreshConnection();
      if (next?.status === "READY") {
        clearPortalApiKey();
      } else if (healthPayload?.checks) {
        const failed = Object.entries(
          healthPayload.checks as Record<string, boolean>,
        )
          .filter(([, ok]) => !ok)
          .map(([key]) => key);
        if (failed.length) {
          setError(`Health failed: ${failed.join(", ")}`);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Register failed");
      await refreshConnection();
    } finally {
      setBusy(false);
    }
  }, [apiBaseUrl, authHeaders, pin, refreshConnection]);

  useEffect(() => {
    const status = connection?.status;
    if (!status || busy || !apiKey.trim()) return;
    if (status === "WEBHOOK_PENDING" && autoStepRef.current !== "webhook") {
      autoStepRef.current = "webhook";
      void submitWebhook();
      return;
    }
    if (status === "HEALTH_CHECK_PENDING" && autoStepRef.current !== "health") {
      autoStepRef.current = "health";
      void submitHealth();
    }
  }, [apiKey, busy, connection?.status, submitHealth, submitWebhook]);

  const submitRetry = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const response = await fetch(
        `${apiBaseUrl.replace(/\/$/, "")}/v1/whatsapp/retry`,
        { method: "POST", headers: authHeaders() },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message =
          payload?.error?.message || `Retry failed (${response.status})`;
        const correlation = payload?.error?.correlation_id;
        throw new Error(correlation ? `${message} (${correlation})` : message);
      }
      setConnection(mapConnection(payload as Record<string, unknown>));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setBusy(false);
    }
  }, [apiBaseUrl, authHeaders]);

  if (connection?.status === "PHONE_PENDING") {
    return (
      <div className="panel">
        <p className="eyebrow">{connection.status}</p>
        <h2>{connection.message}</h2>
        <p className="copy">
          Enter the 6-digit WhatsApp Cloud API PIN to register this phone.
          Messaging stays disabled until later provisioning steps complete.
        </p>
        {connection.phoneNumberId ? (
          <p className="meta">
            Phone number id <code>{connection.phoneNumberId}</code>
            {relative ? (
              <>
                <br />
                Zadnja promjena {relative}
              </>
            ) : null}
          </p>
        ) : null}
        <label className="field">
          <span>Registration PIN</span>
          <input
            type="password"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))}
            placeholder="••••••"
          />
        </label>
        <button
          type="button"
          className="cta"
          onClick={() => void submitPin()}
          disabled={busy || pin.length !== 6}
        >
          {busy ? "Registering…" : "Register phone"}
        </button>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </div>
    );
  }

  if (connection?.status === "WEBHOOK_PENDING") {
    return (
      <div className="panel">
        <p className="eyebrow">{connection.status}</p>
        <h2>{connection.message}</h2>
        <p className="copy">
          Subscribe this WABA to the OmniMsg app webhook. Hub challenge verify
          is handled at the platform gateway; this step only confirms Graph
          subscription for your business account.
        </p>
        {connection.wabaId ? (
          <p className="meta">
            WABA <code>{connection.wabaId}</code>
            {relative ? (
              <>
                <br />
                Zadnja promjena {relative}
              </>
            ) : null}
          </p>
        ) : null}
        <button
          type="button"
          className="cta"
          onClick={() => void submitWebhook()}
          disabled={busy}
        >
          {busy ? "Provisioning…" : "Provision webhook"}
        </button>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </div>
    );
  }

  if (connection?.status === "HEALTH_CHECK_PENDING") {
    return (
      <div className="panel">
        <p className="eyebrow">{connection.status}</p>
        <h2>{connection.message}</h2>
        <p className="copy">
          Run the final health checks against Meta. Messaging is enabled only
          when all six criteria pass and status becomes READY.
        </p>
        <button
          type="button"
          className="cta"
          onClick={() => void submitHealth()}
          disabled={busy}
        >
          {busy ? "Checking…" : "Run health check"}
        </button>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </div>
    );
  }

  if (connection?.status === "READY") {
    return (
      <div className="panel success">
        <p className="eyebrow">{connection.status}</p>
        <h2>{connection.message}</h2>
        <p className="copy">WhatsApp is fully ready for messaging.</p>
        {connection.phoneNumberId ? (
          <p className="meta">
            Phone number id <code>{connection.phoneNumberId}</code>
            {connection.wabaId ? (
              <>
                <br />
                WABA <code>{connection.wabaId}</code>
              </>
            ) : null}
            {relative ? (
              <>
                <br />
                Zadnja promjena {relative}
              </>
            ) : null}
          </p>
        ) : null}
      </div>
    );
  }

  if (connection?.status === "ERROR") {
    return (
      <div className="panel">
        <p className="eyebrow">{connection.status}</p>
        <h2>{connection.message}</h2>
        <p className="copy">
          {connection.lastError ||
            "Provisioning failed. Retry resumes from the recorded recovery target."}
        </p>
        {connection.statusReason ? (
          <p className="meta">
            Reason <code>{connection.statusReason}</code>
            {connection.recoveryTarget ? (
              <>
                {" "}
                · recovery <code>{connection.recoveryTarget}</code>
              </>
            ) : null}
          </p>
        ) : null}
        {connection.recoveryTarget === "EMBEDDED_SIGNUP_STARTED" ? (
          <>
            <p className="copy">
              This error requires reconnecting via Embedded Signup.
            </p>
            <button
              type="button"
              className="cta"
              onClick={launch}
              disabled={busy || !sdkReady || !apiKey.trim()}
            >
              {busy ? "Connecting…" : "Connect WhatsApp"}
            </button>
          </>
        ) : (
          <button
            type="button"
            className="cta"
            onClick={() => void submitRetry()}
            disabled={busy || !connection.recoveryTarget}
          >
            {busy ? "Retrying…" : "Retry"}
          </button>
        )}
        {error ? <p className="error" role="alert">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="panel">
      <p className="eyebrow">WhatsApp</p>
      <h2>Connect WhatsApp</h2>
      <p className="copy">
        {hideApiKeyInput
          ? "Launch Meta Embedded Signup to connect your WhatsApp Business account. After the popup, enter the 6-digit PIN — webhook and health continue automatically."
          : "Paste the tenant API key for this workspace (from your invite), then launch Meta Embedded Signup. After PIN, webhook and health continue automatically."}
      </p>
      {connection ? (
        <p className="meta">
          Status <code>{connection.status}</code>
          {connection.statusReason ? (
            <>
              {" "}
              · <code>{connection.statusReason}</code>
            </>
          ) : null}
          {relative ? <> · Zadnja promjena {relative}</> : null}
          {connection.lastError ? (
            <>
              <br />
              {connection.lastError}
            </>
          ) : null}
        </p>
      ) : null}
      {hideApiKeyInput ? null : (
        <label className="field">
          <span>API key</span>
          <input
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => persistKey(e.target.value)}
            placeholder="omni_…"
          />
        </label>
      )}
      <button
        type="button"
        className="cta"
        onClick={launch}
        disabled={busy || !sdkReady || !apiKey.trim()}
      >
        {busy ? "Connecting…" : sdkReady ? "Connect WhatsApp" : "Loading Meta…"}
      </button>
      {error ? <p className="error" role="alert">{error}</p> : null}
    </div>
  );
}
