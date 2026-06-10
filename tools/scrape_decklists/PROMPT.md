# Decklist Scraper — delegated mission prompt

You are filling a **decklist corpus** for the Simmander deckbuilder's SP3 co-occurrence
pipeline. Your only job is to fetch **raw decklists** from public sources and append them, as
dumb JSON-lines, to `data/decklists/`. You compute **nothing** — no lift, no synergy, no
statistics. All math happens later in tested, deterministic code. If you are tempted to compute
a number, stop: just record the raw cards.

## The contract (exact)

Append to `data/decklists/<source>-<batch>.jsonl`, one JSON object per line.

**Deck record** (a real decklist):
```json
{"kind": "deck", "deck_id": "moxfield:AbC123", "source": "moxfield", "commander": "Atraxa, Praetors' Voice", "card_names": ["Sol Ring", "Cultivate", "Doubling Season"]}
```
- `deck_id` = `"<source>:<native_id>"` — the dedup key. Never invent ids.
- `commander` = the commander's exact card name, or `null` if none/unknown.
- `card_names` = mainboard card names as printed. **Exclude** sideboard / maybeboard /
  considering / removed. Include the commander in the list. Basics are fine to include.
- Do not resolve names to ids — that happens downstream via the card DB.

**EDHREC aggregate record** (commander→card, EDHREC's own published numbers):
```json
{"kind": "edhrec", "commander": "Atraxa, Praetors' Voice", "cards": [{"name": "Doubling Season", "synergy": 0.62, "inclusion": 0.71}]}
```
- Use EDHREC's published `synergy` and `inclusion` verbatim. Do not recompute or renormalize.

## How to fetch (reuse proven code)

A working harness already exists: **`tools/scrape_decklists/runner.py`**. It handles append,
dedup (`data/decklists/.seen_deck_ids`), throttling (≥2s/req), and the Archidekt source.

- **Archidekt** — implemented. `python tools/scrape_decklists/runner.py archidekt --ids <id1>,<id2>`.
  Native ids are the number in `archidekt.com/decks/<id>/`.
- **Moxfield** — implement `_fetch_moxfield` in `runner.py`: GET
  `https://api2.moxfield.com/v3/decks/all/<publicId>`, take `boards.mainboard` (+ `commanders`),
  skip `sideboard`/`maybeboard`, return `(commander, card_names)` in the same shape as Archidekt.
- **EDHREC** — implement `_fetch_edhrec`: GET `https://json.edhrec.com/pages/commanders/<slug>.json`
  (slug rules + a reference parser live in `../../../simmander/sim/edhrec_fetcher.py`). Emit the
  `edhrec` record kind. EDHREC commander pages also link *other* commanders and decklists — good
  seeds to widen coverage.

To discover ids at scale: EDHREC commander pages and Archidekt/Moxfield "search/trending"
endpoints list many public deck ids. Seed from popular commanders, expand outward.

## Rules

1. **Compute nothing.** Raw cards + EDHREC's own numbers only.
2. **Respect the sources.** ≥2s between requests (the harness throttles — don't bypass it),
   identify via the existing User-Agent, honor robots/ToS, public decks only. If a source rate-
   limits or blocks, back off and switch sources; do not hammer.
3. **Append-only & idempotent.** Never rewrite existing lines. Re-running must only *add* decks.
   Trust `.seen_deck_ids` for dedup.
4. **Aim for breadth.** Many commanders, many archetypes — co-occurrence needs variety, not just
   the top 5 decks. A few thousand decks across diverse commanders is the goal; more is better.
5. **Report.** At the end, print how many deck + edhrec records you added and from which sources.

## Definition of done (for one run)

`data/decklists/` has grown by your batch; `.seen_deck_ids` covers them; every line validates
against the contract above (kind, required keys, non-empty `card_names`). Mining code will be
run separately against whatever you've accumulated — you do not run it.
