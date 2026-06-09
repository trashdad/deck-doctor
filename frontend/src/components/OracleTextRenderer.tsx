"use client";

import { splitAbilities, extractVariants } from "@/lib/oracle";
import { useOracle } from "@/store/oracle";

const TRIGGER_RE = /^(whenever|when |at the beginning|at the end|at the start)/i;

export function OracleTextRenderer({ text }: { text: string }) {
  const openPhrase = useOracle((s) => s.openPhrase);
  const abilities = splitAbilities(text);

  return (
    <div className="space-y-1">
      {abilities.map((ability, i) => {
        const triggered = TRIGGER_RE.test(ability);
        return (
          <p
            key={i}
            onClick={(e) => {
              e.stopPropagation();
              openPhrase(extractVariants(ability));
            }}
            title="Click to find cards with similar text"
            className={[
              "cursor-pointer rounded px-1.5 py-0.5 text-[11px] leading-snug transition-colors",
              triggered
                ? "text-amber-200/90 hover:bg-amber-400/10 hover:ring-1 hover:ring-amber-400/25"
                : "text-zinc-300/80 hover:bg-white/5 hover:ring-1 hover:ring-white/10",
            ].join(" ")}
          >
            {ability}
          </p>
        );
      })}
    </div>
  );
}
