"use client";

/*
 * /dev/ui-kit — backend-free gallery of every framework state (plan §7.5).
 * Unlinked; builds in production so Playwright can hit it on simtrack.
 * `?motion=0` forces every transition to 0 s.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Card, Cut, Reason, Suggestion } from "@/lib/types";
import { useUI } from "@/store/ui";
import { useCuts } from "@/store/cuts";
import { useDeck } from "@/store/deck";
import { usePreview } from "@/store/preview";
import { useBackToClose } from "@/lib/useBackToClose";
import { useUndoableDeck, useUndoHotkeys } from "@/hooks/useUndoableDeck";
import { CardFrame, type CardSize, type CardState } from "@/components/card/CardFrame";
import { CardInteractive } from "@/components/card/CardInteractive";
import { CardSurface } from "@/components/card/CardSurface";
import { CardPreview } from "@/components/card/CardPreview";
import { CardContextMenu } from "@/components/card/CardContextMenu";
import { CardSheet, CardSheetBody } from "@/components/card/CardSheet";
import { CardActionsProvider, type PageActionDeps } from "@/components/card/CardActionsContext";
import { buildCardActions } from "@/components/card/cardActions";
import { ReasonLine } from "@/components/reason/ReasonLine";
import { DeckHeader } from "@/components/workbench/DeckHeader";
import { DoctorRail } from "@/components/workbench/DoctorRail";
import { RailTabs } from "@/components/workbench/RailTabs";
import { RailRow } from "@/components/workbench/rail/RailRow";
import { ToastHost } from "@/components/feedback/ToastHost";
import { toast } from "@/components/feedback/toastStore";
import { toRect } from "@/store/preview";
import {
  FIXTURE_CARDS,
  arcaneSignet,
  blasphemous,
  bolt,
  bombardment,
  crimsonWisps,
  dragonTempest,
  hullbreaker,
  isochron,
  krenko,
  mountain,
  rhystic,
  rift,
  skullclamp,
  solRing,
  swords,
  urDragon,
} from "./fixtures";

// ---- Fixture reasons: the backend's own format strings (suggest.py / doctor.py);
// numbers are the ones its unit tests pin (−0.15 / 50 % for cuts, 1.2 for engine). FIXTURE.
const R = {
  edhrec: { signal: "edhrec", value: 0.69, detail: "EDHREC synergy with Krenko, Mob Boss" } as Reason,
  inclusion: { signal: "edhrec_inclusion", value: 0.64, detail: "in 64% of Krenko, Mob Boss decks on EDHREC" } as Reason,
  cooccurrence: { signal: "cooccurrence", value: 0.25, detail: "played alongside 4 of your cards" } as Reason,
  synergy: { signal: "synergy", value: 0.5, detail: "mechanical synergy with 3 of your cards" } as Reason,
  engine: { signal: "engine", value: 1.2, detail: "completes combo → Infinite mana: Isochron Scepter + Dramatic Reversal" } as Reason,
  staple: { signal: "staple", value: 0.05, detail: "format staple in your colors (generic fallback)" } as Reason,
  cutEdhrec: { signal: "edhrec", value: 0.5, detail: "EDHREC: in 50% of this commander's decks (synergy -0.15)" } as Reason,
  cutCooc: { signal: "cooccurrence", value: 0.1, detail: "played with 2 of your other cards" } as Reason,
  cutStaple: { signal: "staple", value: 1.0, detail: "corpus staple (1.0 = the most-played card)" } as Reason,
  unknown: { signal: "anti_synergy", value: -0.3, detail: "conflicts with Blasphemous Act" } as Reason,
};

const SUGGESTIONS: Suggestion[] = [
  { card: skullclamp, score: 0.9, reasons: [R.inclusion, R.cooccurrence, R.synergy] },
  { card: isochron, score: 0.8, reasons: [R.engine, R.cooccurrence] },
  { card: bombardment, score: 0.7, reasons: [R.edhrec, R.synergy] },
  { card: solRing, score: 0.05, reasons: [R.staple] },
];
const CUTS: Cut[] = [
  { card: crimsonWisps, contribution: 0.02, reasons: [R.cutEdhrec, R.cutCooc] },
  { card: arcaneSignet, contribution: 0.4, reasons: [R.cutStaple, R.cutCooc] },
];

const FIND_CARDS: Card[] = [skullclamp, solRing, arcaneSignet, bolt, blasphemous, rhystic, bombardment, isochron, hullbreaker, dragonTempest, mountain, swords];
const PILE_CARDS: Card[] = [solRing, arcaneSignet, skullclamp, bolt, blasphemous, bombardment];
const NO_ART: Card = { ...crimsonWisps, id: "fixture-no-art", image_uris: null };

function Section({ id, title, note, children }: { id: string; title: string; note?: string; children: React.ReactNode }) {
  return (
    <section data-testid={`kit-${id}`} className="rounded-lg border border-edge bg-panel-solid p-4">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-accent">{title}</h2>
      {note && <p className="mt-1 text-[13px] leading-[18px] text-zinc-400">{note}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <span className="block text-[11px] text-zinc-400">{children}</span>;
}

/** Shows which side the open preview picked for a given anchor card (placement cases). */
function SideLabel({ cardId }: { cardId: string }) {
  const open = usePreview((s) => s.open);
  const anchorId = usePreview((s) => s.anchorId);
  const [side, setSide] = useState<string>("—");
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      if (open && anchorId === cardId) {
        setSide(document.querySelector('[data-testid="card-preview"]')?.getAttribute("data-side") ?? "?");
      } else if (!open) {
        setSide("—");
      }
    });
    return () => cancelAnimationFrame(id);
  }, [open, anchorId, cardId]);
  return (
    <span data-testid="side-label" className="text-[11px] font-semibold text-cyan">
      side: {side}
    </span>
  );
}

export default function UiKitPage() {
  const menu = useUI((s) => s.menu);
  const sheet = useUI((s) => s.sheet);
  const closeMenu = useUI((s) => s.closeMenu);
  const closeSheet = useUI((s) => s.closeSheet);
  const openMenu = useUI((s) => s.openMenu);
  const railTab = useUI((s) => s.railTab);
  const setRailTab = useUI((s) => s.setRailTab);
  const pushRail = useUI((s) => s.pushRail);
  const cuts = useCuts();
  const deck = useUndoableDeck();
  const deckCards = useDeck((s) => s.cards);
  const liveCount = Object.keys(deckCards).length;
  const [dialogOpen, setDialogOpen] = useState(false);
  useUndoHotkeys();

  // Back closes the menu / sheet (M6).
  const closeOverlays = useCallback(() => {
    closeMenu();
    closeSheet();
    setDialogOpen(false);
  }, [closeMenu, closeSheet]);
  useBackToClose(Boolean(menu) || Boolean(sheet) || dialogOpen, closeOverlays);

  // ?motion=0 → deterministic screenshots.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("motion") === "0") document.documentElement.dataset.motion = "0";
  }, []);

  // A modal dialog suppresses the preview (P7).
  useEffect(() => {
    if (!dialogOpen) return;
    return usePreview.getState().suppress();
  }, [dialogOpen]);

  const deps = useMemo<PageActionDeps>(
    () => ({
      deck: {
        add: (c) => deck.add(c),
        remove: (c) => deck.remove(c),
        move: (c, z) => deck.move(c, z),
        setCommander: (c, p) => deck.setCommander(c, p),
      },
      cuts: { toggle: cuts.toggle, has: cuts.has },
      explorer: (card, axis) => pushRail({ kind: "explorer", card, axis }),
      semantic: (card) => pushRail({ kind: "semantic", card }),
      upgrade: (card) => pushRail({ kind: "upgrade", card }),
      commanders: [krenko],
    }),
    [deck, cuts.toggle, cuts.has, pushRail],
  );

  const openCornerMenu = (corner: "tl" | "tr" | "bl" | "br", btn: HTMLElement) => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const at = { tl: { x: 4, y: 4 }, tr: { x: vw - 4, y: 4 }, bl: { x: 4, y: vh - 4 }, br: { x: vw - 4, y: vh - 4 } }[corner];
    openMenu({ model: buildCardActions("deck", krenko, { ...deps, zone: "Commanders" }), title: krenko.name, subtitle: krenko.type_line, at, returnFocusTo: btn, via: "pointer" });
  };

  const sizes: CardSize[] = ["pile", "tile", "thumb", "hero"];
  const states: { label: string; state: CardState; card?: Card }[] = [
    { label: "default", state: {} },
    { label: "hover", state: { forceHover: true } },
    { label: "ghost · additional", state: { ghost: "additional" } },
    { label: "ghost · bridge", state: { ghost: "bridge" } },
    { label: "off-color", state: { offColor: true }, card: swords },
    { label: "cut candidate", state: { cutCandidate: true } },
    { label: "selected", state: { selected: true } },
    { label: "dragging", state: { dragging: true } },
    { label: "wincon", state: { wincon: true }, card: krenko },
    { label: "IER pill (fixture 14)", state: { ierPill: "14" } },
    { label: "art missing", state: {}, card: NO_ART },
  ];

  return (
    <CardActionsProvider deps={deps}>
      <main className="mx-auto flex w-full max-w-[1400px] flex-col gap-4 px-4 py-4 text-zinc-200">
        <header className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="arcade-bevel text-[13px] sm:text-sm">UI KIT</h1>
          <p className="text-[13px] text-zinc-400">
            Fixtures only — {FIXTURE_CARDS.length} real cards from data/cards.json; no backend. Live deck count:{" "}
            <span data-testid="deck-count-live" className="font-semibold text-zinc-100">{liveCount}</span>
          </p>
        </header>

        {/* 1. CardFrame × size × state */}
        <Section id="frames" title="1 · CardFrame — sizes × states" note="Art first; badges on the two top corners only; hover = 1 px gold ring + 2 px lift (10 px on piles), no scale.">
          <div className="flex flex-col gap-4">
            {sizes.map((size) => (
              <div key={size} className="flex flex-col gap-1">
                <Label>size · {size}</Label>
                <div className="flex flex-wrap items-end gap-3">
                  {states.map((s) => (
                    <div key={s.label} className="flex flex-col items-center gap-1" style={size === "hero" ? { width: 120 } : undefined}>
                      <CardFrame card={s.card ?? skullclamp} size={size} state={s.state} tabIndex={s.label === "default" ? 0 : undefined} />
                      <Label>{s.label}</Label>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Section>

        {/* 2. CardInteractive per context */}
        <Section id="contexts" title="2 · CardInteractive — contexts" note="Hover to preview (120 ms). Right-click / Shift+F10 / click for the menu. Tab into a surface, arrows move. Touch: tap or long-press opens the sheet.">
          <div className="flex flex-col gap-5">
            <div>
              <Label>find · grid of 12, as wide as the Find rail (Enter = Add)</Label>
              <CardSurface id="find" orientation="grid" label="Find results" data-testid="kit-find" className="mt-1 flex w-fit max-w-full flex-wrap gap-3 rounded border border-dashed border-edge p-3 md:max-w-[560px]">
                {FIND_CARDS.map((c) => (
                  <CardInteractive key={c.id} card={c} size="tile" context="find" surfaceId="find" primary={() => deck.add(c)} state={{ offColor: c.id === swords.id }}>
                    <div className="dd-actions">
                      <button type="button" title="Add to deck" className="text-accent hover:bg-accent/20" onClick={() => deck.add(c)}>＋</button>
                      <button type="button" title="Focus explorer on this card" className="text-cyan hover:bg-cyan/20" onClick={() => deps.explorer(c, "similar")}>◎</button>
                    </div>
                  </CardInteractive>
                ))}
              </CardSurface>
            </div>
            <div className="flex flex-wrap gap-8">
              <div>
                <Label>deck · pile of 6 (←→, Enter = menu, Del = remove, M = move)</Label>
                <CardSurface id="pile-ramp" orientation="row" label="Ramp lane" data-testid="kit-pile" className="mt-1 flex items-start rounded border border-dashed border-edge px-3 pb-2 pt-4" style={{ paddingTop: 16 }}>
                  {PILE_CARDS.map((c, i) => (
                    <CardInteractive key={c.id} card={c} size="pile" context="deck" surfaceId="pile-ramp" zone="Ramp" onRemove={() => deck.remove(c)} state={{ cutCandidate: cuts.candidates.has(c.id) }} style={{ marginLeft: i === 0 ? 0 : -44, zIndex: i }} />
                  ))}
                </CardSurface>
              </div>
              <div>
                <Label>commander · strip</Label>
                <CardSurface id="commander" orientation="row" label="Commanders" data-testid="kit-commander" className="mt-1 flex gap-3 rounded border border-dashed border-edge p-3">
                  <CardInteractive card={krenko} size="tile" context="commander" surfaceId="commander" state={{ wincon: true }} />
                  <CardInteractive card={urDragon} size="tile" context="commander" surfaceId="commander" />
                </CardSurface>
              </div>
            </div>
            <div>
              <Label>rail rows · suggest / cut / tune-up ("?" toggles why)</Label>
              <CardSurface id="kit-rows" orientation="column" label="Rail rows" data-testid="kit-rows" className="mt-1 w-full max-w-[400px] rounded border border-dashed border-edge">
                <ul>
                  <RailRow card={skullclamp} context="suggest" surfaceId="kit-rows" role="Card Draw" quotaNote="Draw → 10/10" reasons={[R.inclusion, R.cooccurrence, R.synergy]} commanderName={krenko.name} primaryLabel="+" primaryTitle="Add to deck" onPrimary={() => deck.add(skullclamp)} />
                  <RailRow card={crimsonWisps} context="cut" surfaceId="kit-rows" role="Utility" quotaNote="31 → 30" reasons={[R.cutEdhrec, R.cutCooc]} commanderName={krenko.name} primaryLabel="Cut" primaryTitle="Cut from deck" primaryTone="danger" onPrimary={() => deck.remove(crimsonWisps)} note="cmc 1 · the curve's 1-drop bin is at 14 (template 9)" />
                  <RailRow card={rhystic} context="tuneup" surfaceId="kit-rows" role="Card Draw" reasons={[R.edhrec, R.cooccurrence]} commanderName={krenko.name} primaryLabel="Swap" primaryTitle="Swap in" onPrimary={() => deck.add(rhystic)} warning="conflicts with Blasphemous Act" />
                </ul>
              </CardSurface>
            </div>
          </div>
        </Section>

        {/* 3. Preview placement cases */}
        <Section id="placement" title="3 · CardPreview — placement cases" note="Dashed box = the [data-surface]. The preview sits beside the surface (right → left → below → above), never over it when a side fits.">
          <div data-testid="kit-placement-stage" className="relative h-[460px] w-full overflow-hidden rounded border border-edge/60 bg-ink/40">
            {(
              [
                { key: "left", card: bolt, cls: "left-2 top-1/2 -translate-y-1/2" },
                { key: "right", card: rift, cls: "right-2 top-2" },
                { key: "top", card: rhystic, cls: "left-[38%] top-2" },
                { key: "bottom", card: hullbreaker, cls: "left-[58%] bottom-2" },
                { key: "narrow", card: dragonTempest, cls: "right-2 bottom-2" },
              ] as const
            ).map((c) => (
              <CardSurface
                key={c.key}
                id={`place-${c.key}`}
                orientation="row"
                label={`Placement ${c.key}`}
                data-testid={`place-${c.key}`}
                className={`absolute flex flex-col items-center gap-1 rounded border border-dashed border-cyan/60 p-2 ${c.cls}`}
              >
                <CardInteractive card={c.card} size={c.key === "narrow" ? "pile" : "tile"} context="find" surfaceId={`place-${c.key}`} />
                <span className="text-[11px] text-zinc-400">{c.key}</span>
                <SideLabel cardId={c.card.id} />
              </CardSurface>
            ))}
          </div>
        </Section>

        {/* 4. Menu corners */}
        <Section id="menu" title="4 · CardContextMenu — corners + keyboard" note="Opened programmatically at each viewport corner (M5); the last button opens it keyboard-style, anchored to itself.">
          <div className="flex flex-wrap gap-2">
            {(["tl", "tr", "bl", "br"] as const).map((corner) => (
              <button key={corner} type="button" data-testid={`menu-${corner}`} onClick={(e) => openCornerMenu(corner, e.currentTarget)} className="h-9 rounded border border-accent/50 px-3 text-[13px] font-semibold text-accent hover:bg-accent/10">
                Open at {corner.toUpperCase()}
              </button>
            ))}
            <button
              type="button"
              data-testid="menu-keyboard"
              onClick={(e) => {
                const el = e.currentTarget;
                const surface = el.closest("[data-testid='kit-menu']") as HTMLElement;
                openMenu({ model: buildCardActions("find", skullclamp, deps), title: skullclamp.name, subtitle: skullclamp.type_line, at: { anchorRect: toRect(el.getBoundingClientRect()), surfaceRect: toRect(surface.getBoundingClientRect()) }, returnFocusTo: el, via: "keyboard" });
              }}
              className="h-9 rounded border border-cyan/50 px-3 text-[13px] font-semibold text-cyan hover:bg-cyan/10"
            >
              Open via keyboard
            </button>
            <button type="button" data-testid="open-dialog" onClick={() => setDialogOpen(true)} className="h-9 rounded border border-edge px-3 text-[13px] text-zinc-300 hover:border-accent/50">
              Open a modal dialog
            </button>
          </div>
        </Section>

        {/* 5. Sheet inline */}
        <Section id="sheet" title="5 · CardSheet — inline at 390 px" note="The touch path: large image, name/type, then the same actions as the menu as 44 px rows.">
          <div className="w-[390px] max-w-full overflow-hidden rounded-[14px] border border-edge">
            <CardSheetBody inline card={krenko} model={buildCardActions("deck", krenko, { ...deps, zone: "Commanders" })} onClose={() => toast({ message: "Sheet close pressed (inline demo)" })} />
          </div>
        </Section>

        {/* 6. ReasonLine */}
        <Section id="reasons" title="6 · ReasonLine — every signal" note="Sentence first; numbers are chips after it; why ▾ lists every reason with the backend's raw detail.">
          <ul className="grid gap-3 md:grid-cols-2">
            {(
              [
                ["edhrec", [R.edhrec]],
                ["edhrec_inclusion", [R.inclusion]],
                ["cooccurrence", [R.cooccurrence]],
                ["synergy", [R.synergy]],
                ["engine", [R.engine]],
                ["staple", [R.staple]],
                ["cut · edhrec (verbatim)", [R.cutEdhrec, R.cutCooc], "cut"],
                ["unknown signal (verbatim)", [R.unknown]],
                ["mixed · lead + 3 chips", [R.inclusion, R.cooccurrence, R.synergy, R.staple]],
              ] as [string, Reason[], "cut"?][]
            ).map(([label, reasons, ctx]) => (
              <li key={label} data-testid="reason-case" className="rounded border border-edge/70 p-3">
                <Label>{label}</Label>
                <ReasonLine reasons={reasons} commanderName={krenko.name} context={ctx ?? "suggest"} className="mt-1" />
              </li>
            ))}
          </ul>
        </Section>

        {/* 7. DeckHeader states */}
        <Section id="header" title="7 · DeckHeader — count pill × ledger × bracket" note="87 (under), 100 (at), 103 (over). Bracket shows a floor and its flags, never a bare number.">
          <div className="flex flex-col gap-3">
            <DeckHeader commander={krenko} count={87} target={100} ledger={[{ zone: "Lands", have: 30, quota: 36 }, { zone: "Ramp", have: 7, quota: 10 }, { zone: "Card Draw", have: 6, quota: 10 }, { zone: "Removal", have: 5, quota: 9 }, { zone: "Board Wipes", have: 1, quota: 3 }]} curve={[{ cmc: 1, count: 8 }, { cmc: 2, count: 14 }, { cmc: 3, count: 16 }, { cmc: 4, count: 10 }, { cmc: 5, count: 5 }, { cmc: 6, count: 3 }]} bracket={{ floor: 2, flags: [] }} onOpenCuts={() => {}} onOpenComplete={() => toast({ message: "Complete would open here" })} onJumpToLane={() => {}} onFlagClick={() => {}} className="!static" />
            <DeckHeader commander={krenko} count={100} target={100} ledger={[{ zone: "Lands", have: 36, quota: 36 }, { zone: "Ramp", have: 10, quota: 10 }, { zone: "Card Draw", have: 10, quota: 10 }, { zone: "Removal", have: 9, quota: 9 }, { zone: "Board Wipes", have: 3, quota: 3 }]} curve={[{ cmc: 1, count: 9 }, { cmc: 2, count: 16 }, { cmc: 3, count: 18 }, { cmc: 4, count: 11 }, { cmc: 5, count: 6 }, { cmc: 6, count: 3 }, { cmc: 7, count: 1 }]} bracket={{ floor: 3, flags: ["fast mana"] }} onOpenCuts={() => {}} onOpenComplete={() => {}} onJumpToLane={() => {}} onFlagClick={() => {}} className="!static" />
            <DeckHeader commander={null} count={103} target={100} ledger={[{ zone: "Lands", have: 36, quota: 36 }, { zone: "Ramp", have: 12, quota: 10 }, { zone: "Card Draw", have: 11, quota: 10 }, { zone: "Removal", have: 9, quota: 9 }, { zone: "Board Wipes", have: 4, quota: 3 }]} curve={[{ cmc: 1, count: 14 }, { cmc: 2, count: 18 }, { cmc: 3, count: 16 }, { cmc: 4, count: 9 }, { cmc: 5, count: 6 }, { cmc: 8, count: 2 }]} bracket={{ floor: 4, flags: ["fast mana", "1 combo pair", "extra turns"] }} onOpenCuts={(n) => { cuts.setTarget(n); setRailTab("cuts"); }} onOpenComplete={() => {}} onJumpToLane={() => {}} onFlagClick={(f) => toast({ message: `Would highlight cards flagged: ${f}` })} className="!static" />
          </div>
        </Section>

        {/* 8. Toast */}
        <Section id="toast" title="8 · Toast with Undo">
          <button type="button" data-testid="show-toast" onClick={() => toast({ message: "Added Skullclamp to Card Draw", action: { label: "Undo", onClick: () => {} } })} className="h-9 rounded border border-accent/50 px-3 text-[13px] font-semibold text-accent hover:bg-accent/10">
            Show toast
          </button>
        </Section>

        {/* 9. Workbench composition */}
        <Section id="workbench" title="9 · Workbench — header + board + rail" note="The deck is never hidden by advice: the rail is a column beside the board, not a drawer over it. 1–5 switch tabs; Ctrl/⌘+Z undoes.">
          <div className="flex flex-col overflow-hidden rounded border border-edge lg:h-[560px] lg:flex-row">
            <div className="flex min-h-0 min-w-0 flex-1 flex-col">
              <DeckHeader commander={krenko} count={103} target={100} ledger={[{ zone: "Lands", have: 36, quota: 36 }, { zone: "Ramp", have: 12, quota: 10 }, { zone: "Card Draw", have: 9, quota: 10 }, { zone: "Removal", have: 9, quota: 9 }, { zone: "Board Wipes", have: 4, quota: 3 }]} curve={[{ cmc: 1, count: 14 }, { cmc: 2, count: 18 }, { cmc: 3, count: 16 }, { cmc: 4, count: 9 }, { cmc: 5, count: 6 }, { cmc: 8, count: 2 }]} bracket={{ floor: 3, flags: ["fast mana", "1 combo pair"] }} onOpenCuts={(n) => { cuts.setTarget(n); setRailTab("cuts"); }} onOpenComplete={() => {}} onJumpToLane={(z) => toast({ message: `Would scroll to ${z}` })} onFlagClick={(f) => toast({ message: `Would highlight cards flagged: ${f}` })} className="!static" />
              <div data-testid="engine-board" className="min-h-[260px] flex-1 overflow-y-auto bg-panel-solid p-3">
                {(
                  [
                    ["Win Conditions", "board-wincon", [krenko, bombardment] as Card[]],
                    ["Ramp", "board-ramp", [solRing, arcaneSignet, mountain] as Card[]],
                    ["Removal", "board-removal", [bolt, blasphemous, rift] as Card[]],
                  ] as const
                ).map(([lane, id, cardsInLane]) => (
                  <div key={id} className="dd-lane mb-3">
                    <p className="dd-lane-title">{lane}</p>
                    <CardSurface id={id} orientation="row" label={`${lane} lane`} className="flex items-start px-1 pb-1 pt-3">
                      {cardsInLane.map((c, i) => (
                        <CardInteractive key={c.id} card={c} size="pile" context="deck" surfaceId={id} zone={lane} onRemove={() => deck.remove(c)} state={{ wincon: lane === "Win Conditions", cutCandidate: cuts.candidates.has(c.id) }} style={{ marginLeft: i === 0 ? 0 : -44, zIndex: i }} />
                      ))}
                    </CardSurface>
                  </div>
                ))}
              </div>
              <div className="lg:hidden">
                <RailTabs value={railTab} onChange={setRailTab} variant="bar" />
              </div>
            </div>
            <DoctorRail
              commander={krenko}
              count={103}
              suggest={{ tier: "edhrec", suggestions: SUGGESTIONS }}
              cuts={{ target: cuts.target, candidates: CUTS, onTargetChange: cuts.setTarget }}
              onAdd={(c) => deck.add(c)}
              onCut={(c) => deck.remove(c)}
              className="hidden lg:flex"
            />
          </div>
        </Section>
      </main>

      {dialogOpen && (
        <div role="dialog" aria-modal="true" aria-label="Demo dialog" data-testid="demo-dialog" className="fixed inset-0 z-dialog flex items-center justify-center bg-black/40" onClick={() => setDialogOpen(false)}>
          <div className="rounded-lg border border-accent/40 bg-panel p-6 text-[13px]" onClick={(e) => e.stopPropagation()}>
            <p>A modal dialog is open — previews are suppressed.</p>
            <button type="button" onClick={() => setDialogOpen(false)} className="mt-3 h-9 rounded border border-accent/50 px-3 font-semibold text-accent">Close</button>
          </div>
        </div>
      )}

      <CardPreview />
      <CardContextMenu />
      <CardSheet />
      <ToastHost />
    </CardActionsProvider>
  );
}
