# Deck Export (Text / Moxfield CSV / Archidekt CSV / ManaPool) — Design Spec

**Date:** 2026-06-11 · **Status:** approved (build-it-all directive), ready to plan
**Sub-feature B.** Export the deck the user is building to multiple formats, plus a ManaPool
"add all to cart" handoff. Works on the **current working deck** (saved or not).

## Goal
From the deck the user is building, produce a copy/download in: **Text** (already supported for saved
decks), **Moxfield CSV**, **Archidekt CSV**, and **ManaPool** (decklist text + an "add all to cart"
deep-link to ManaPool's mass-entry tool).

## Backend (`backend/app/export.py` new + one route)
Pure formatters over a resolved deck (no DB, no auth — it just formats the cards the client sends).
- `to_text(rows) -> str` — the existing `// Zone` / `Commander:` / `N Name` format (extract from the
  current `/decks/{id}/export` logic so both share it; DRY).
- `to_moxfield_csv(rows) -> str` — header + rows. Moxfield import accepts a CSV whose key columns are
  `Count,Name,Edition,Condition,Language,Foil,Collector Number`. Emit `Count,Name` populated and the rest
  blank/defaults (`1,Sol Ring,,,,,`)? **The implementer MUST verify the current Moxfield CSV import header
  against moxfield.com before finalizing** (Moxfield is picky); fall back to the minimal `Count,Name` it
  accepts. Commander rows included (Moxfield infers commander from the deck, so just list it).
- `to_archidekt_csv(rows) -> str` — Archidekt deck CSV import columns: `Quantity,Name,Finish,Condition,
  Edition Code,Collector Number,Category`. Populate `Quantity,Name,Category` (Category = our zone, e.g.
  "Commander" for the commander, others by zone); rest defaults. **Verify the current Archidekt CSV import
  header before finalizing.**
- `to_manapool(rows) -> str` — ManaPool mass-entry paste format: one `「qty」 「name」` line per card (e.g.
  `1 Sol Ring`), commander included. (Documented accepted format; see the research note in the program memory.)
- **Route:** `POST /deck/export?format=text|moxfield|archidekt|manapool` body = `DeckRequest`
  (`{commander_id, cards}`); resolves ids→names via the store; returns `text/plain` (PlainTextResponse).
  Unknown format → 400. No auth (formats client-provided cards). Keep the existing
  `GET /decks/{id}/export` (saved-deck text export) working — it can delegate to `to_text`.
- Tests (`backend/tests/test_export.py`): each format returns the expected shape for a small deck
  (commander + a few cards); round-trip the **text** format back through `/decks/import` with 0 unresolved;
  ManaPool lines match `^\d+ .+$`; CSV has the right header row + one row per distinct card; bad format → 400.

## Frontend (`lib/api.ts` + an Export panel)
- `lib/api.ts`: `exportDeck(entries, commanderId, format) -> Promise<string>` → `POST /deck/export?format=…`.
- **`components/ExportPanel.tsx`** (or extend the existing `ImportExportDialog.tsx`): an "Export" affordance
  (header button `📤 Export`, enabled when the deck is non-empty) opening a small panel with one button per
  format:
  - **Text / Moxfield CSV / Archidekt CSV** → fetch the formatted string → trigger a file download
    (`deck.txt` / `deck-moxfield.csv` / `deck-archidekt.csv`) AND offer "Copy to clipboard".
  - **ManaPool → "Add all to cart"**: fetch the ManaPool-format decklist, **copy it to the clipboard**,
    and open `https://manapool.com/add-deck` in a new tab (with the affiliate `?ref=`/`?partner=` params
    when configured — that config is owned by sub-feature C; read it from a shared
    `lib/affiliate.ts::manapoolAddDeckUrl()` which returns the base URL + ref when set, else the bare URL).
    Show a toast: "Decklist copied — paste it into ManaPool's mass-entry box." (The `deck=` prefill param
    is undocumented; clipboard-paste is the reliable, EDHREC-proven handoff.)
- Keep the existing amber/jewel styling (reuse the SuggestionsPanel/TemplatePanel chrome).

## Out of scope / notes
- The `?ref=` affiliate value comes from **sub-feature C** (`lib/affiliate.ts`, env-configured). B's
  ManaPool button works without it (bare URL) and gains the ref automatically once C lands.
- No per-printing/set selection in v1 (export by name + quantity; "Any Printings" on ManaPool).
- Foil/condition columns are emitted blank (singleton Commander decks).
