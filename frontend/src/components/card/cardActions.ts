import type { Card } from "@/lib/types";
import { ZONES, type Zone } from "@/lib/zones";
import { canHavePartner, isValidPartner } from "@/lib/partners";
import { amazonCardUrl, manapoolCardUrl, tcgplayerCardUrl } from "@/lib/affiliate";
import type { CardContext } from "@/store/ui";
import type { ReactNode } from "react";
import { ICONS } from "@/components/menu/icons";

export type { CardContext };

export type MenuModel = MenuGroup[];

export interface MenuGroup {
  id: string;
  items: MenuItemModel[];
}

export interface MenuItemModel {
  id: string;
  label: string;
  /** Keyboard hint shown in the right-hand column. */
  shortcut?: string;
  /** One of the menu icon set (menu/icons.tsx) — same size and stroke for every row. */
  icon?: ReactNode;
  tone?: "primary" | "danger" | "default";
  /** Rendered but inert (aria-disabled, skipped by roving focus). Hidden items are omitted instead. */
  disabled?: boolean;
  href?: string;
  external?: boolean;
  submenu?: MenuItemModel[];
  /** Radio-style check (used by the "Move to …" submenu for the current zone). */
  checked?: boolean;
  /** A single row carrying several links (the buy row). */
  links?: { label: string; href: string }[];
  onSelect?: () => void;
}

export type ExplorerAxis = "similar" | "synergy" | "cooccurrence" | "combos";

export interface ActionDeps {
  deck: {
    add: (card: Card) => void;
    remove: (card: Card) => void;
    move: (card: Card, zone: Zone) => void;
    setCommander: (card: Card, asPartner?: boolean) => void;
  };
  cuts: { toggle: (id: string) => void; has: (id: string) => boolean };
  explorer: (card: Card, axis: ExplorerAxis) => void;
  semantic: (card: Card) => void;
  upgrade: (card: Card) => void;
  why?: () => void;
  /** Current commander(s) in the deck. */
  commanders: Card[];
  /** Deck context: the lane the card currently sits in. */
  zone?: Zone;
}

/** Exact-name Scryfall search — needs no id mapping (§4.7.3). */
export function scryfallUrl(name: string): string {
  return `https://scryfall.com/search?q=${encodeURIComponent(`!"${name}"`)}`;
}

const isLegendaryCreature = (card: Card) => (card.type_line ?? "").includes("Legendary Creature");

/**
 * Context-dependent action list, in the order of plan §4.7.3. Hidden items are
 * omitted, not disabled. Pure — unit-testable against the gallery.
 */
export function buildCardActions(ctx: CardContext, card: Card, deps: ActionDeps): MenuModel {
  const primary: MenuItemModel[] = [];
  const inDeck = ctx === "deck" || ctx === "commander";
  const isCommander = deps.commanders.some((c) => c.id === card.id);

  if (ctx === "find" || ctx === "suggest" || ctx === "combos" || ctx === "explorer") {
    primary.push({
      id: "add",
      label: "Add to deck",
      shortcut: "Enter",
      icon: ICONS.add,
      tone: "primary",
      onSelect: () => deps.deck.add(card),
    });
  }
  if (inDeck) {
    primary.push({
      id: "remove",
      label: "Remove from deck",
      shortcut: "Del",
      icon: ICONS.remove,
      tone: "danger",
      onSelect: () => deps.deck.remove(card),
    });
  }
  if (isLegendaryCreature(card) && !isCommander) {
    primary.push({
      id: "set-commander",
      label: "Set as commander",
      icon: ICONS.commander,
      onSelect: () => deps.deck.setCommander(card, false),
    });
  }
  if (
    deps.commanders.length === 1 &&
    !isCommander &&
    canHavePartner(deps.commanders[0]) &&
    isValidPartner(card, deps.commanders[0])
  ) {
    primary.push({
      id: "add-partner",
      label: "Add as partner",
      icon: ICONS.partner,
      onSelect: () => deps.deck.setCommander(card, true),
    });
  }
  if (ctx === "deck") {
    primary.push({
      id: "move",
      label: "Move to …",
      shortcut: "→",
      icon: ICONS.move,
      submenu: ZONES.map((z) => ({
        id: `move:${z}`,
        label: z,
        checked: deps.zone === z,
        onSelect: () => deps.deck.move(card, z),
      })),
    });
    const flagged = deps.cuts.has(card.id);
    primary.push({
      id: "cut",
      label: flagged ? "Unmark cut candidate" : "Mark as cut candidate",
      shortcut: "✂",
      icon: ICONS.cut,
      onSelect: () => deps.cuts.toggle(card.id),
    });
    primary.push({
      id: "upgrade",
      label: "Swap for a better card",
      icon: ICONS.upgrade,
      onSelect: () => deps.upgrade(card),
    });
  }
  if ((ctx === "suggest" || ctx === "cut" || ctx === "tuneup") && deps.why) {
    primary.push({ id: "why", label: "Why this card?", shortcut: "?", icon: ICONS.why, onSelect: deps.why });
  }

  const explore: MenuItemModel[] = [
    { id: "similar", label: "Similar cards", icon: ICONS.similar, onSelect: () => deps.explorer(card, "similar") },
    { id: "synergy", label: "Synergizes with", icon: ICONS.synergy, onSelect: () => deps.explorer(card, "synergy") },
    { id: "played", label: "Played with", icon: ICONS.played, onSelect: () => deps.explorer(card, "cooccurrence") },
    { id: "combos", label: "Combos & engines", icon: ICONS.combos, onSelect: () => deps.explorer(card, "combos") },
    { id: "semantic", label: "Find cards that do this…", icon: ICONS.semantic, onSelect: () => deps.semantic(card) },
  ];

  const external: MenuItemModel[] = [
    { id: "scryfall", label: "View on Scryfall", shortcut: "↗", icon: ICONS.scryfall, href: scryfallUrl(card.name), external: true },
    {
      id: "buy",
      label: "Buy",
      icon: ICONS.buy,
      links: [
        { label: "ManaPool", href: manapoolCardUrl(card.name) },
        { label: "TCGplayer", href: tcgplayerCardUrl(card.name) },
        { label: "Amazon", href: amazonCardUrl(card.name) },
      ],
    },
  ];

  const groups: MenuModel = [];
  if (primary.length) groups.push({ id: "primary", items: primary });
  groups.push({ id: "explore", items: explore });
  groups.push({ id: "external", items: external });
  return groups;
}

/** Flat label list in order — handy for tests (M2). */
export function menuLabels(model: MenuModel): string[] {
  return model.flatMap((g) => g.items.map((i) => i.label));
}
