"use client";

import { useMemo, type ReactNode } from "react";
import type { DeckCard, BasicEntry } from "@/store/deck";
import { useDeck } from "@/store/deck";
import { useTemplateStore, COMPOSITE_TEMPLATE_ID } from "@/store/template";
import { useUI } from "@/store/ui";
import { cardFunctions, cardEngines, matchingZones } from "@/lib/functions";
import type { Zone } from "@/lib/zones";
import type { PileEntry } from "./CardPile";
import type { ColumnSections, EngineKey } from "./EngineColumn";
import { CommanderStrip } from "./CommanderStrip";
import { EngineColumn } from "./EngineColumn";
import { EngineStaplesPanel } from "./EngineStaplesPanel";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function addToSection(
  map: Partial<Record<Zone, PileEntry[]>>,
  zone: Zone,
  entry: PileEntry,
) {
  if (!map[zone]) map[zone] = [];
  map[zone]!.push(entry);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * Engine Board — replaces the flat ZoneColumn grid.
 * Reads deck state + template store, runs the placement algorithm, renders
 * CommanderStrip + engine columns (or single column for non-composite).
 */
export function EngineBoard({
  commanderControls,
}: {
  /** Deck-action controls rendered in the right of the commander pane. */
  commanderControls?: ReactNode;
}) {
  const { cards, basics, remove } = useDeck();
  const selectedId = useTemplateStore((s) => s.selectedId);
  const composite = useTemplateStore((s) => s.composite);
  const themes = useTemplateStore((s) => s.themes);
  const setThemeA = useTemplateStore((s) => s.setThemeA);
  const setThemeB = useTemplateStore((s) => s.setThemeB);
  const setThemeC = useTemplateStore((s) => s.setThemeC);
  const openEngineStaples = useUI((s) => s.openEngineStaples);

  const isComposite = selectedId === COMPOSITE_TEMPLATE_ID;

  // Resolve theme tag sets and labels for engine matching
  const themeAInfo = useMemo(
    () => (isComposite && composite.themeA ? themes.find((t) => t.id === composite.themeA) : null),
    [isComposite, composite.themeA, themes],
  );
  const themeBInfo = useMemo(
    () => (isComposite && composite.themeB ? themes.find((t) => t.id === composite.themeB) : null),
    [isComposite, composite.themeB, themes],
  );
  const themeCInfo = useMemo(
    () => (isComposite && composite.themeC ? themes.find((t) => t.id === composite.themeC) : null),
    [isComposite, composite.themeC, themes],
  );

  const themeATags = themeAInfo?.tags ?? [];
  const themeBTags = themeBInfo?.tags ?? [];
  const themeCTags = themeCInfo?.tags ?? [];

  // Commander(s) (used in the render). The rest of the deck is derived inside the
  // placement memo below so the deps are the stable store references.
  const commanders = Object.values(cards)
    .filter((dc) => dc.zone === "Commanders")
    .map((dc) => dc.card);

  // ---------------------------------------------------------------------------
  // Placement algorithm
  // ---------------------------------------------------------------------------
  const { e1Sections, e2Sections, e3Sections, neutralSections, singleSections } = useMemo(() => {
    const e1: Partial<Record<Zone, PileEntry[]>> = {};
    const e2: Partial<Record<Zone, PileEntry[]>> = {};
    const e3: Partial<Record<Zone, PileEntry[]>> = {};
    const neutral: Partial<Record<Zone, PileEntry[]>> = {};
    const single: Partial<Record<Zone, PileEntry[]>> = {};

    const nonCommanderCards = Object.values(cards).filter((dc) => dc.zone !== "Commanders");
    const basicEntries = Object.values(basics);

    // Basics → Lands (solid). Neutral in composite (lands rarely match a theme).
    for (const b of basicEntries) {
      const entry: PileEntry = { card: b.card, variant: "solid" };
      addToSection(isComposite ? neutral : single, "Lands", entry);
    }

    for (const dc of nonCommanderCards) {
      const fns = cardFunctions(dc.card);
      // Honor a manual drag-rehome: dc.zone overrides the derived home; the
      // remaining matching functions still show as ghosts.
      const home: Zone = dc.zone !== fns.home ? (dc.zone as Zone) : fns.home;
      const additional = matchingZones(dc.card).filter((z) => z !== home);

      if (isComposite) {
        const eng = cardEngines(dc.card, themeATags, themeBTags, themeCTags);

        // Solid engine = first match by priority e1 > e2 > e3, else neutral.
        const solidEngine: EngineKey = eng.e1
          ? "e1"
          : eng.e2
            ? "e2"
            : eng.e3
              ? "e3"
              : "neutral";

        const target =
          solidEngine === "e1"
            ? e1
            : solidEngine === "e2"
              ? e2
              : solidEngine === "e3"
                ? e3
                : neutral;

        addToSection(target, home, { card: dc.card, variant: "solid" });
        for (const z of additional) {
          addToSection(target, z, { card: dc.card, variant: "ghost", ghostKind: "additional" });
        }

        // Bridge ghosts: for each OTHER engine the card also matches, emit a
        // 50%-ghost in that engine's copy of the card's home field.
        if (solidEngine !== "e2" && eng.e2) {
          addToSection(e2, home, { card: dc.card, variant: "ghost", ghostKind: "bridge" });
        }
        if (solidEngine !== "e3" && eng.e3) {
          addToSection(e3, home, { card: dc.card, variant: "ghost", ghostKind: "bridge" });
        }
        // e1 bridge: only needed when solid is e2 or e3 and the card also matches e1
        // (rare, since priority already puts e1-matching cards into e1 as solid)
        if (solidEngine !== "e1" && eng.e1) {
          addToSection(e1, home, { card: dc.card, variant: "ghost", ghostKind: "bridge" });
        }
      } else {
        addToSection(single, home, { card: dc.card, variant: "solid" });
        for (const z of additional) {
          addToSection(single, z, { card: dc.card, variant: "ghost", ghostKind: "additional" });
        }
      }
    }

    return {
      e1Sections: e1,
      e2Sections: e2,
      e3Sections: e3,
      neutralSections: neutral,
      singleSections: single,
    };
  }, [cards, basics, isComposite, themeATags, themeBTags, themeCTags]);

  const hasNeutral = Object.values(neutralSections).some((arr) => arr && arr.length > 0);

  // ---------------------------------------------------------------------------
  // Staples button handlers
  // ---------------------------------------------------------------------------
  const handleStaplesE1 = themeAInfo
    ? () => openEngineStaples({ engineKey: "e1", themeId: composite.themeA, themeLabel: themeAInfo.label })
    : undefined;
  const handleStaplesE2 = themeBInfo
    ? () => openEngineStaples({ engineKey: "e2", themeId: composite.themeB, themeLabel: themeBInfo.label })
    : undefined;
  const handleStaplesE3 = themeCInfo
    ? () => openEngineStaples({ engineKey: "e3", themeId: composite.themeC, themeLabel: themeCInfo.label })
    : undefined;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4 scrollbar-thin">
      {/* Commander strip — always present */}
      <CommanderStrip commanders={commanders} onRemove={remove} controls={commanderControls} />

      {isComposite ? (
        /* ── COMPOSITE: engine columns always visible (red | blue | green | neutral) ──
           Each engine carries its own theme dropdown so you can set it up front;
           cards flow in as soon as a theme is picked. */
        <div className="flex items-start gap-3">
          <EngineColumn
            engineKey="e1"
            label="Engine 1"
            themeValue={composite.themeA}
            themeOptions={themes}
            onThemeChange={setThemeA}
            onStaples={handleStaplesE1}
            sections={e1Sections}
            onRemove={remove}
          />
          <EngineColumn
            engineKey="e2"
            label="Engine 2"
            themeValue={composite.themeB}
            themeOptions={themes}
            onThemeChange={setThemeB}
            onStaples={handleStaplesE2}
            sections={e2Sections}
            onRemove={remove}
          />
          <EngineColumn
            engineKey="e3"
            label="Engine 3"
            themeValue={composite.themeC}
            themeOptions={themes}
            onThemeChange={setThemeC}
            onStaples={handleStaplesE3}
            sections={e3Sections}
            onRemove={remove}
          />
          {/* Theme-less cards live in a neutral column BESIDE the engines, not below. */}
          {hasNeutral && (
            <EngineColumn
              engineKey="neutral"
              label="Neutral"
              themeLabel="no engine"
              sections={neutralSections}
              onRemove={remove}
            />
          )}
        </div>
      ) : (
        /* ── SINGLE-COLUMN MODE: function fields stacked ── */
        <EngineColumn
          engineKey="single"
          sections={singleSections}
          onRemove={remove}
        />
      )}

      {/* Engine Staples panel — self-hides when engineStaples store is null */}
      <EngineStaplesPanel />
    </div>
  );
}
