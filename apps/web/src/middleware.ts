import { NextRequest, NextResponse } from "next/server";

import {
  marketingOrigin,
  normalizeHost,
  portalOrigin,
  surfaceForHost,
} from "@/lib/hosts";

export function middleware(request: NextRequest) {
  const host = normalizeHost(request.headers.get("host"));
  const surface = surfaceForHost(host);
  const { pathname } = request.nextUrl;

  if (surface === null) {
    return new NextResponse("Not Found", { status: 404 });
  }

  // Canonicalize internal path prefixes if hit on the wrong host.
  if (pathname === "/www" || pathname.startsWith("/www/")) {
    if (surface === "portal") {
      const url = new URL(pathname.replace(/^\/www/, "") || "/", marketingOrigin(host));
      return NextResponse.redirect(url);
    }
  }
  if (pathname === "/portal" || pathname.startsWith("/portal/")) {
    if (surface === "marketing") {
      const url = new URL(pathname.replace(/^\/portal/, "") || "/", portalOrigin(host));
      return NextResponse.redirect(url);
    }
  }

  // App Review static demos under public/app-review/ — skip /www|/portal rewrite.
  if (pathname === "/app-review" || pathname.startsWith("/app-review/")) {
    if (!pathname.endsWith(".html")) {
      const reviewUrl = request.nextUrl.clone();
      reviewUrl.pathname = `${pathname.replace(/\/$/, "")}/index.html`;
      return NextResponse.rewrite(reviewUrl);
    }
    return NextResponse.next();
  }

  const url = request.nextUrl.clone();
  if (surface === "marketing") {
    if (!pathname.startsWith("/www")) {
      url.pathname = pathname === "/" ? "/www" : `/www${pathname}`;
      return NextResponse.rewrite(url);
    }
  } else if (surface === "portal") {
    if (!pathname.startsWith("/portal")) {
      url.pathname = pathname === "/" ? "/portal" : `/portal${pathname}`;
      return NextResponse.rewrite(url);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Skip Next internals and static brand assets.
     */
    "/((?!_next/static|_next/image|favicon.ico|brand/|icon.png|apple-icon.png).*)",
  ],
};
