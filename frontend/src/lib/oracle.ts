// Oracle text phrase extraction — powers the clickable-text side panel.

export interface PhraseVariant {
  label: string;   // display text (may be truncated with …)
  pattern: string; // exact substring sent to the API
}

const TRIGGER_PREFIXES = [
  "whenever",
  "when ",
  "at the beginning",
  "at the end",
  "at the start",
];

function isTrigger(ability: string): boolean {
  const low = ability.toLowerCase();
  return TRIGGER_PREFIXES.some((p) => low.startsWith(p));
}

function firstCommaIdx(text: string): number {
  // Find the comma that separates the trigger from effects, skipping nested clauses.
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "(") depth++;
    else if (text[i] === ")") depth--;
    else if (text[i] === "," && depth === 0) return i;
  }
  return -1;
}

function splitEffects(rest: string): string[] {
  // Split "each opponent loses 1 life and you gain 1 life" into sub-effects.
  // We split on " and " but only at the top level (not inside parentheses).
  const parts: string[] = [];
  let depth = 0;
  let cur = "";
  const words = rest.split(/\b(and)\b/i);
  for (const chunk of words) {
    if (chunk.toLowerCase() === "and" && depth === 0 && cur.trim()) {
      parts.push(cur.trim());
      cur = "";
    } else {
      for (const ch of chunk) {
        if (ch === "(") depth++;
        else if (ch === ")") depth--;
      }
      cur += chunk;
    }
  }
  if (cur.trim()) parts.push(cur.trim());
  // Also split on "; "
  return parts
    .flatMap((p) => p.split(/;\s+/))
    .map((p) => p.replace(/\.$/, "").trim())
    .filter(Boolean);
}

function truncate(s: string, max = 60): string {
  return s.length > max ? s.slice(0, max - 1).trimEnd() + "…" : s;
}

/** Given one ability string, return a list of search variants from broad → specific. */
export function extractVariants(ability: string): PhraseVariant[] {
  const clean = ability.replace(/\.$/, "").trim();

  if (!isTrigger(ability)) {
    return [{ label: truncate(clean), pattern: clean }];
  }

  const commaIdx = firstCommaIdx(clean);
  if (commaIdx === -1) {
    return [{ label: truncate(clean), pattern: clean }];
  }

  const trigger = clean.slice(0, commaIdx).trim();
  const rest = clean.slice(commaIdx + 1).trim();
  const effects = splitEffects(rest);

  const variants: PhraseVariant[] = [];

  // Broadest: just the trigger
  variants.push({ label: truncate(trigger) + "…", pattern: trigger });

  // Mid: trigger + each individual sub-effect
  if (effects.length > 1) {
    for (const eff of effects) {
      const phrase = `${trigger}, ${eff}`;
      variants.push({ label: truncate(phrase), pattern: phrase });
    }
  }

  // Most specific: full ability
  variants.push({ label: truncate(clean), pattern: clean });

  // Deduplicate by pattern
  const seen = new Set<string>();
  return variants.filter((v) => {
    if (seen.has(v.pattern)) return false;
    seen.add(v.pattern);
    return true;
  });
}

/** Split oracle text into individual ability lines. */
export function splitAbilities(oracleText: string): string[] {
  return oracleText
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}
