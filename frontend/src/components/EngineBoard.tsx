"use client";

import { useMemo } from "react";
import type { DeckCard, BasicEntry } from "@/store/deck";
import { useDeck } from "@/store/deck";
import { useTemplateStore, COMPOSITE_TEMPLATE_ID } from "@/store/template";
import { cardFunctions, cardEngines, matchingZones } from "@/lib/functions";
import type { Zone } from "@/lib/zones";
import type { PileEntry } from "./CardPile";
import type { ColumnSections, EngineKey } from "./EngineColumn";
import { CommanderStrip } from "./CommanderStrip";
import { EngineColumn } from "./EngineColumn";

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
export function EngineBoard() {
  const { cards, basics, remove } = useDeck();
  const selectedId = useTemplateStore((s) => s.selectedId);
  const composite = useTemplateStore((s) => s.composite);
  const themes = useTemplateStore((s) => s.themes);
  const setThemeA = useTemplateStore((s) => s.setThemeA);
  const setThemeB = useTemplateStore((s) => s.setThemeB);

  const isComposite = selectedId === COMPOSITE_TEMPLATE_ID;

  // Resolve theme tag sets for engine matching
  const themeATags = useMemo(() => {
    if (!isComposite || !composite.themeA) return [];
    return themes.find((t) => t.id === composite.themeA)?.tags ?? [];
  }, [isComposite, composite.themeA, themes]);

  const themeBTags = useMemo(() => {
    if (!isComposite || !composite.themeB) return [];
    return themes.find((t) => t.id === composite.themeB)?.tags ?? [];
  }, [isComposite, composite.themeB, themes]);

  // Commander (used in the render). The rest of the deck is derived inside the
  // placement memo below so the deps are the stable store references.
  const commander =
    Object.values(cards).find((dc) => dc.zone === "Commanders")?.card ?? null;

  // ---------------------------------------------------------------------------
  // Placement algorithm
  // ---------------------------------------------------------------------------
  const { e1Sections, e2Sections, neutralSections, singleSections } = useMemo(() => {
    const e1: Partial<Record<Zone, PileEntry[]>> = {};
    const e2: Partial<Record<Zone, PileEntry[]>> = {};
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
        const eng = cardEngines(dc.card, themeATags, themeBTags);
        const solidEngine: EngineKey = eng.e1 ? "e1" : eng.e2 ? "e2" : "neutral";
        const target = solidEngine === "e1" ? e1 : solidEngine === "e2" ? e2 : neutral;

        addToSection(target, home, { card: dc.card, variant: "solid" });
        for (const z of additional) {
          addToSection(target, z, { card: dc.card, variant: "ghost", ghostKind: "additional" });
        }
        // Bridge ghost in E2's home field when the card serves both engines.
        if (eng.e1 && eng.e2) {
          addToSection(e2, home, { card: dc.card, variant: "ghost", ghostKind: "bridge" });
        }
      } else {
        addToSection(single, home, { card: dc.card, variant: "solid" });
        for (const z of additional) {
          addToSection(single, z, { card: dc.card, variant: "ghost", ghostKind: "additional" });
        }
      }
    }

    return { e1Sections: e1, e2Sections: e2, neutralSections: neutral, singleSections: single };
  }, [cards, basics, isComposite, themeATags, themeBTags]);

  // Handle drag-drop re-home: the EngineBoard passes the remove handler down;
  // move is handled by the DndContext in page.tsx (same as ZoneColumn).

  const hasNeutral = Object.values(neutralSections).some((arr) => arr && arr.length > 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4 scrollbar-thin">
      {/* Commander strip — always present */}
      <CommanderStrip
        commander={commander}
        onRemove={commander ? () => remove(commander.id) : undefined}
      />

      {isComposite ? (
        /* ── COMPOSITE: engine columns always visible (red | blue | neutral) ──
           Each engine carries its own theme dropdown so you can set it up front;
           cards flow in as soon as a theme is picked. */
        <div className="flex items-start gap-3">
          <EngineColumn
            engineKey="e1"
            label="Engine 1"
            themeValue={composite.themeA}
            themeOptions={themes}
            onThemeChange={setThemeA}
            sections={e1Sections}
            onRemove={remove}
          />
          <EngineColumn
            engineKey="e2"
            label="Engine 2"
            themeValue={composite.themeB}
            themeOptions={themes}
            onThemeChange={setThemeB}
            sections={e2Sections}
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
    </div>
  );
}
