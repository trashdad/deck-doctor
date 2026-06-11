/** @type {import('next').NextConfig} */
// Deck Doctor is hosted under a path on simmander.app (simmander.app/deck-doctor),
// so every route + asset is served beneath this prefix. Set NEXT_PUBLIC_BASE_PATH=""
// to host at a domain root instead. Keep in sync with lib/api.ts BASE_PATH.
const BASE_PATH =
  process.env.NEXT_PUBLIC_BASE_PATH === "" ? "" : process.env.NEXT_PUBLIC_BASE_PATH || "/deck-doctor";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output bundles a minimal server for the Docker runtime image (SP11).
  output: "standalone",
  // basePath also auto-prefixes the /api rewrite below (→ {BASE_PATH}/api/*).
  ...(BASE_PATH ? { basePath: BASE_PATH } : {}),
  images: {
    // Real Magic card art is served from Scryfall's CDN. When Phase 0 confirms
    // simmander's own image host, add it here.
    remotePatterns: [
      { protocol: "https", hostname: "cards.scryfall.io" },
      { protocol: "https", hostname: "*.scryfall.io" },
    ],
  },
  async rewrites() {
    // In Docker, BACKEND_ORIGIN points at the backend service (e.g. http://backend:8001).
    const api =
      process.env.BACKEND_ORIGIN ||
      process.env.NEXT_PUBLIC_API_BASE ||
      "http://localhost:8001";
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;
