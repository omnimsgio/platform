/** Host → surface helpers for middleware and metadata. */

export type Surface = "marketing" | "portal";

const MARKETING_HOSTS = new Set([
  "omnimsg.io",
  "www.omnimsg.io",
  "omnimsgio-web.localhost",
]);

const PORTAL_HOSTS = new Set([
  "app.omnimsg.io",
  "omnimsgio-app.localhost",
]);

export function normalizeHost(hostHeader: string | null): string {
  if (!hostHeader) return "";
  return hostHeader.split(":")[0].trim().toLowerCase();
}

export function surfaceForHost(host: string): Surface | null {
  if (MARKETING_HOSTS.has(host)) return "marketing";
  if (PORTAL_HOSTS.has(host)) return "portal";
  // Local Next.dev without Traefik: treat bare localhost as marketing.
  if (host === "localhost" || host === "127.0.0.1") return "marketing";
  return null;
}

export function marketingOrigin(host: string): string {
  if (host.endsWith(".localhost") || host === "localhost" || host === "127.0.0.1") {
    return "https://omnimsgio-web.localhost";
  }
  return "https://omnimsg.io";
}

export function portalOrigin(host: string): string {
  if (host.endsWith(".localhost") || host === "localhost" || host === "127.0.0.1") {
    return "https://omnimsgio-app.localhost";
  }
  return "https://app.omnimsg.io";
}
