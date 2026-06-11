"use client";

import { useMemo } from "react";
import type { DeckCard, BasicEntry } from "@/store/deck";
import { useDeck } from "@/store/deck";
import { useTemplateStore, COMPOSITE_TEMPLATE_ID } from "@/store/template";
import { cardFunctions, cardEngines } from "@/lib/functions";
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

  const themeALabel = useMemo(
    () => (composite.themeA ? themes.find((t) => t.id === composite.themeA)?.label ?? "" : ""),
    [composite.themeA, themes],
  );
  const themeBLabel = useMemo(
    () => (composite.themeB ? themes.find((t) => t.id === composite.themeB)?.label ?? "" : ""),
    [composite.themeB, themes],
  );

  // Separate commander from non-commander deck cards
  const deckCards = Object.values(cards);
  const commander = deckCards.find((dc) => dc.zone === "Commanders")?.card ?? null;
  const nonCommanderCards = deckCards.filter((dc) => dc.zone !== "Commanders");

  // Basic lands go into the Lands section as solid cards
  const basicEntries = Object.values(basics);

  // ---------------------------------------------------------------------------
  // Placement algorithm
  // ---------------------------------------------------------------------------
  const { e1Sections, e2Sections, neutralSections, singleSections } = useMemo(() => {
    const e1: Partial<Record<Zone, PileEntry[]>> = {};
    const e2: Partial<Record<Zone, PileEntry[]>> = {};
    const neutral: Partial<Record<Zone, PileEntry[]>> = {};
    const single: Partial<Record<Zone, PileEntry[]>> = {};

    // Add basics to Lands
    for (const b of basicEntries) {
      const entry: PileEntry = { card: b.card, variant: "solid" };
      if (isComposite) {
        // Basics are neutral (lands rarely match theme tags)
        addToSection(neutral, "Lands", entry);
      } else {
        addToSection(single, "Lands", entry);
      }
    }

    for (const dc of nonCommanderCards) {
      const fns = cardFunctions(dc.card);

      if (isComposite) {
        const eng = cardEngines(dc.card, themeATags, themeBTags);
        const solidEngine: EngineKey =
          eng.e1 ? "e1" : eng.e2 ? "e2" : "neutral";

        // Solid in home field of solid engine
        const solidEntry: PileEntry = { card: dc.card, variant: "solid" };
        if (solidEngine === "e1") {
          addToSection(e1, fns.home, solidEntry);
        } else if (solidEngine === "e2") {
          addToSection(e2, fns.home, solidEntry);
        } else {
          addToSection(neutral, fns.home, solidEntry);
        }

        // Additional ghosts in same engine, other function subsections
        for (const addlZone of fns.additional) {
          const ghostEntry: PileEntry = {
            card: dc.card,
            variant: "ghost",
            ghostKind: "additional",
          };
          if (solidEngine === "e1") {
            addToSection(e1, addlZone, ghostEntry);
          } else if (solidEngine === "e2") {
            addToSection(e2, addlZone, ghostEntry);
          } else {
            addToSection(neutral, addlZone, ghostEntry);
          }
        }

        // Bridge ghost: if card matches both engines, emit 50% ghost in E2's home field
        if (eng.e1 && eng.e2) {
          const bridgeEntry: PileEntry = {
            card: dc.card,
            variant: "ghost",
            ghostKind: "bridge",
          };
          addToSection(e2, fns.home, bridgeEntry);
        }
      } else {
        // Non-composite: single column
        const solidEntry: PileEntry = { card: dc.card, variant: "solid" };
        addToSection(single, fns.home, solidEntry);

        // Additional ghosts
        for (const addlZone of fns.additional) {
          const ghostEntry: PileEntry = {
            card: dc.card,
            variant: "ghost",
            ghostKind: "additional",
          };
          addToSection(single, addlZone, ghostEntry);
        }
      }
    }

    return { e1Sections: e1, e2Sections: e2, neutralSections: neutral, singleSections: single };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    nonCommanderCards,
    basicEntries,
    isComposite,
    themeATags,
    themeBTags,
  ]);

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
        /* ── COMPOSITE MODE: two engine columns + optional neutral ── */
        <div className="flex flex-col gap-4">
          {/* Engine columns row */}
          <div className="relative flex gap-0">
            {/* Gilded divider */}
            <div
              className="pointer-events-none absolute inset-y-2 left-1/2 z-10 w-px -translate-x-px"
              style={{
                background:
                  "linear-gradient(180deg, transparent, rgba(201,162,39,0.65), transparent)",
              }}
            />

            <EngineColumn
              engineKey="e1"
              label="Engine 1"
              themeLabel={themeALabel || undefined}
              sections={e1Sections}
              onRemove={remove}
            />
            <EngineColumn
              engineKey="e2"
              label="Engine 2"
              themeLabel={themeBLabel || undefined}
              sections={e2Sections}
              onRemove={remove}
            />
          </div>

          {/* Neutral column — full width, below */}
          {hasNeutral && (
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <div className="h-px flex-1 bg-edge" />
                <span className="text-[10px] uppercase tracking-widest text-zinc-600">
                  Neutral
                </span>
                <div className="h-px flex-1 bg-edge" />
              </div>
              <EngineColumn
                engineKey="neutral"
                sections={neutralSections}
                onRemove={remove}
              />
            </div>
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
