"use client";

import type { Card, DeckCombos, SpellbookCombo } from "@/lib/types";
import { EmptyState } from "./SuggestTab";

export interface CombosTabProps {
  hasCommander: boolean;
  /** `/deck/combos` response (same endpoint DeckCombosPanel uses); undefined = not fetched. */
  data?: DeckCombos;
  loading?: boolean;
  onAdd?: (card: Card) => void;
  onOpenCard?: (card: Card) => void;
}

function ProducesLine({ combo }: { combo: SpellbookCombo }) {
  if (combo.produces.length === 0) return null;
  return <p className="text-[10px] text-fuchsia-200/90">→ {combo.produces.join(", ")}</p>;
}

function MemberChip({ card, onClick }: { card: Card; onClick?: () => void }) {
  return (
    <button
      type="button"
      title={card.name}
      onClick={onClick}
      className="rounded border border-edge bg-panel2/60 px-1 py-0.5 text-[10px] text-zinc-300 hover:border-accent/60"
    >
      {card.name}
    </button>
  );
}

/** Combos tab — DeckCombosPanel's body (complete + one-card-away), fed by the caller's query (§4.6). */
export function CombosTab({ hasCommander, data, loading, onAdd, onOpenCard }: CombosTabProps) {
  if (!data) {
    return (
      <EmptyState testid="combos-panel">
        {hasCommander ? (
          loading ? (
            <>Checking Commander Spellbook…</>
          ) : (
            <>Combos you have and combos you are one card from, with what each needs.</>
          )
        ) : (
          <>
            No commander → <strong>Pick one</strong> (left) or <strong>paste a list</strong> (Import).
          </>
        )}
      </EmptyState>
    );
  }
  const complete = data.complete ?? [];
  const near = data.near ?? [];
  return (
    <div data-testid="combos-panel" className="flex min-h-0 flex-1 flex-col overflow-y-auto p-3 scrollbar-thin">
      <p className="mb-2 font-display text-[9px] uppercase tracking-wider text-accent">In your deck ({complete.length})</p>
      <div data-testid="combos-complete" className="space-y-2">
        {complete.length === 0 && <p className="py-3 text-center text-[11px] text-zinc-600">No complete combos yet.</p>}
        {complete.map((c) => (
          <div key={c.combo_id} className="rounded-lg border border-magenta/40 bg-magenta/[0.06] p-2">
            <ProducesLine combo={c} />
            <div className="mt-1 flex flex-wrap gap-1">
              {c.members.map((m) => (
                <MemberChip key={m.id} card={m} onClick={onOpenCard ? () => onOpenCard(m) : undefined} />
              ))}
            </div>
          </div>
        ))}
      </div>
      <p className="mb-2 mt-4 font-display text-[9px] uppercase tracking-wider text-accent">One card away ({near.length})</p>
      <div data-testid="combos-near" className="space-y-2">
        {near.length === 0 && <p className="py-3 text-center text-[11px] text-zinc-600">No one-card-away combos.</p>}
        {near.map((n) => (
          <div key={n.combo.combo_id} className="rounded-lg border border-accent/50 bg-accent/[0.06] p-2">
            <ProducesLine combo={n.combo} />
            <div className="mt-1 flex items-center justify-between gap-2">
              <p className="truncate text-xs font-semibold text-accent">add {n.missing.name}</p>
              {onAdd && (
                <button
                  type="button"
                  onClick={() => onAdd(n.missing)}
                  className="shrink-0 rounded border border-accent/60 px-2 py-0.5 text-[11px] text-accent hover:bg-accent/10"
                >
                  + Add
                </button>
              )}
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {n.combo.members
                .filter((m) => m.id !== n.missing.id)
                .map((m) => (
                  <MemberChip key={m.id} card={m} onClick={onOpenCard ? () => onOpenCard(m) : undefined} />
                ))}
            </div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[10px] text-zinc-500">
        {complete.length} complete · {near.length} one-away · Commander Spellbook
      </p>
    </div>
  );
}
