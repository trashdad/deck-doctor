import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Deck Doctor — Simmander",
  description:
    "Deck Doctor: a card-art EDH deckbuilder that diagnoses, completes, and tunes your Commander decks. Part of simmander.app.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Rajdhani:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        {/* Fixed synthwave × Golden Axe backdrop: one big slowly-rotating 16-bit
            golden axe behind a sunset sun + neon perspective grid + CRT scanlines.
            Sits behind all app content (z-0); content shells render above it. */}
        <div className="arcade-scene" aria-hidden="true">
          <div className="arcade-sun" />
          <div className="arcade-grid" />
          <div className="arcade-axe" />
          <div className="arcade-scan" />
        </div>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
