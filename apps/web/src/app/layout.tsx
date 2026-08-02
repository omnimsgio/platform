import type { Metadata } from "next";
import { DM_Sans, Sora } from "next/font/google";

import "./globals.css";

const sora = Sora({
  subsets: ["latin"],
  variable: "--font-sora",
  display: "swap",
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://omnimsg.io"),
  title: {
    default: "OmniMsg — One platform. Every message.",
    template: "%s · OmniMsg",
  },
  description:
    "API-first omnichannel messaging. One API. Any channel. Any provider.",
  openGraph: {
    title: "OmniMsg",
    description: "One platform. Every message.",
    url: "https://omnimsg.io",
    siteName: "OmniMsg",
    images: [{ url: "/brand/omnimsg-lockup.png", width: 1254, height: 1254 }],
    type: "website",
  },
  icons: {
    icon: [{ url: "/brand/omnimsg-icon.png", type: "image/png" }],
    apple: [{ url: "/brand/omnimsg-icon.png" }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${sora.variable} ${dmSans.variable}`}>
      <body>{children}</body>
    </html>
  );
}
