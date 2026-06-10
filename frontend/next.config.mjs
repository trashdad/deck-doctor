/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output bundles a minimal server for the Docker runtime image (SP11).
  output: "standalone",
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
