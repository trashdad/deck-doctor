import type { Card } from "./types";

/**
 * Commander partner rules, derived from oracle text + type line.
 *
 * We recognise the real pairing mechanics: generic Partner, "Partner with
 * <name>", Background ("Choose a Background" + Background cards), Friends
 * forever, and Doctor / Doctor's companion. Anything else can't take a partner.
 */

type PartnerKind =
  | { kind: "with"; name: string } // Partner with <specific card>
  | { kind: "partner" } // generic Partner
  | { kind: "chooseBg" } // "Choose a Background" commander
  | { kind: "background" } // a Background card
  | { kind: "friends" } // Friends forever
  | { kind: "doctor" } // a Time Lord Doctor
  | { kind: "companion" } // Doctor's companion
  | null;

function partnerKind(card: Card): PartnerKind {
  const text = (card.oracle_text ?? "").toLowerCase();
  const type = (card.type_line ?? "").toLowerCase();

  const withMatch = text.match(/partner with ([^\n.,(]+)/);
  if (withMatch) return { kind: "with", name: withMatch[1].trim() };
  if (text.includes("choose a background")) return { kind: "chooseBg" };
  if (type.includes("background")) return { kind: "background" };
  if (text.includes("friends forever")) return { kind: "friends" };
  if (text.includes("doctor's companion")) return { kind: "companion" };
  if (type.includes("time lord doctor")) return { kind: "doctor" };
  // Generic Partner (the bare keyword), but only if it isn't one of the above.
  if (/\bpartner\b/.test(text)) return { kind: "partner" };
  return null;
}

/** Can this card legally take a second (partner) commander at all? */
export function canHavePartner(card: Card): boolean {
  return partnerKind(card) !== null;
}

/** Is `candidate` a legal partner for `commander`? */
export function isValidPartner(candidate: Card, commander: Card): boolean {
  if (candidate.id === commander.id) return false;
  const a = partnerKind(commander);
  const b = partnerKind(candidate);
  if (!a || !b) return false;

  switch (a.kind) {
    case "with":
      // The named partner pairs back; match by name in either direction.
      return (
        candidate.name.toLowerCase() === a.name ||
        (b.kind === "with" && commander.name.toLowerCase() === b.name)
      );
    case "partner":
      return b.kind === "partner";
    case "chooseBg":
      return b.kind === "background";
    case "background":
      return b.kind === "chooseBg";
    case "friends":
      return b.kind === "friends";
    case "doctor":
      return b.kind === "companion";
    case "companion":
      return b.kind === "doctor";
    default:
      return false;
  }
}
