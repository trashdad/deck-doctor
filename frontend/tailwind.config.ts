import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Premium dark "tabletop" palette.
        ink: "#0c0a14",
        panel: "#151221",
        panel2: "#1d1930",
        edge: "#2a2540",
        accent: "#c9a227", // antique gold
        accent2: "#7c5cff",
        // MTG pip colors.
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
        display: ["var(--font-display)", "Georgia", "serif"],
      },
      boxShadow: {
        card: "0 6px 20px rgba(0,0,0,0.55)",
        glow: "0 0 0 1px rgba(201,162,39,0.35), 0 8px 30px rgba(124,92,255,0.18)",
      },
      borderRadius: {
        card: "4.75% / 3.5%", // real MTG corner ratio
      },
    },
  },
  plugins: [],
};

export default config;
