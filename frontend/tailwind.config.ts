import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // "Arcade Diagnosis" — synthwave (house theme-synth palette) × Golden Axe.
        // Semantic token NAMES are kept so existing bg-panel/border-accent/text-accent
        // utilities re-skin for free; only the values move.
        ink: "#0a0420", // violet base
        panel: "#150d33",
        panel2: "#1d1242",
        edge: "#3b2a66", // neon-dim border
        accent: "#ffd24a", // gold (was antique gold)
        accent2: "#ff2bd6", // neon magenta (was violet)
        // New synthwave accents.
        cyan: "#00eeff",
        magenta: "#ff2bd6",
        sun: "#ff7ad9",
        bronze: "#a8690f",
        // MTG pip colors (unchanged).
        mana: {
          W: "#f8f5e3",
          U: "#3b82f6",
          B: "#5b4a63",
          R: "#ef4444",
          G: "#22c55e",
          C: "#9aa0a6",
        },
      },
      fontFamily: {
        // Press Start 2P — wordmark + section/zone headers ONLY (it's wide).
        display: ["var(--font-display)", "monospace"],
        // Rajdhani — body / UI text.
        ui: ["var(--font-ui)", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 6px 20px rgba(0,0,0,0.55)",
        glow: "0 0 0 1px rgba(255,210,74,0.35), 0 8px 30px rgba(255,43,214,0.22)",
        neon: "0 0 18px rgba(255,43,214,0.45), 0 0 6px rgba(0,238,255,0.35)",
      },
      borderRadius: {
        card: "4.75% / 3.5%", // real MTG corner ratio
      },
    },
  },
  plugins: [],
};

export default config;
