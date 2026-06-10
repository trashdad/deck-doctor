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
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
