# Template System + Dual-Theme Composite — Design Spec (build-ready)

**Date:** 2026-06-10 · **Status:** approved decisions, researched, ready to implement (no code written yet)
**Feature:** a deck "template" dropdown near the top of the page that sets composition targets
(lands/ramp/removal/…) from expert + data-derived presets, plus an editable dual-theme Composite
that drives a ranked card-suggestion list. The frontend-design skill was invoked for this feature.

## Locked decisions (from the user, 2026-06-10)
1. **Template sources = BOTH** published expert presets (hand-encoded) **and** a data-derived
   "Corpus Average" from our 4,255 scraped decks, **plus** our editable Composite.
2. **Template drives the Deck Doctor:** selecting a template sets the quotas `complete_deck` uses,
   so "Complete my deck" fills to those exact counts.
3. **Theme card list ranked by efficiency + commander synergy** (blend, not pure IER).

## Researched template numbers (counts are land/ramp/card_draw/removal/board_wipe; commander=1; synergy = 99−sum)
Source for Command Zone: commanderdeckmaker.com + edh.fandom.com — **38 / 10 / 8 / 8 / 4** baseline,
with documented archetype variants (control → more removal+wipes+draw; aggro → fewer lands+removal;
combo → more draw+ramp).

| id | name | source | land | ramp | draw | removal | wipe | notes |
|---|---|---|---|---|---|---|---|---|
| `command_zone` | Command Zone | published | 38 | 10 | 8 | 8 | 4 | the famous baseline |
| `control` | Control | published (CZ variant) | 38 | 10 | 10 | 13 | 6 | |
| `aggro` | Aggro | published (CZ variant) | 35 | 8 | 8 | 6 | 2 | |
| `combo` | Combo | published (CZ variant) | 36 | 11 | 11 | 6 | 2 | |
| `corpus_average` | Corpus Average | **data-derived** | 37 | 7 | 9 | 4 | 3 | from 3,249 of our decks ≥80 cards; lands normalized to 37 (scraped lists under-report basics) |
| `simmander_composite` | Simmander Composite | ours, **editable + dual-theme** | 37 | 10 | 9 | 8 | 3 | default; user can edit counts + pick 2 themes |

**Empirical evidence behind Corpus Average** (computed this session over 3,249 scraped decks ≥80 cards,
avg size 90.5 — incomplete lists, so land mean 26 is artificially low and normalized to 37):
non-land means ramp 6.7 · draw 8.8 · removal 3.7 · wipe 3.0 · counters 4.8 · tokens 6.1 · synergy 31.2.
(counters/tokens fold into "synergy" — `doctor.TEMPLATE` only has the 5 quota categories.)

## Theme catalog (verified against the live tag inverted index — 189 tags)
Each theme → a set of semantic tags (flat, "any"); suggestion pool = union of selected themes' cards.
Cards matching BOTH chosen themes get a relevance boost (the dual-theme "bridge" payoff).

| theme | tags (all confirmed present, counts in store) |
|---|---|
| Aristocrats | `e:sacrifice`, `t:creature_dies`, `e:lose_life`, `cost:sacrifice` |
| Landfall / Lands | `perm:land`, `t:landfall`, `e:mana` |
| +1/+1 Counters | `c:plus1`, `e:add_counter`, `e:proliferate` |
| Tokens / Go-wide | `e:create_token`, `t:token_created` |
| Spellslinger | `t:cast_spell`, `e:copy` |
| Reanimator / Graveyard | `e:reanimate`, `e:mill`, `e:discard` |
| Lifegain | `e:gain_life`, `k:lifelink` |
| Voltron (auras/equip) | `k:equip`, `e:pump`, `tgt:self` |
| Blink / Flicker | `e:bounce`, `t:etb` |
| Burn | `e:damage` |
| Mill | `e:mill` |
| Control | `e:counter_spell`, `e:destroy`, `e:board_wipe` |
| Card Draw | `e:draw` |
| Ramp | `e:mana`, `perm:land` |
| Combat / Aggro | `t:attacks`, `t:combat_damage`, `k:trample`, `k:haste` |

Free-text box: parse words against theme labels/aliases → union their tags; unmatched words → fall
back to `store.oracle_search(word)` ∩ candidate pool. Lets the user dial "aristocrat + draw" etc.

## Backend (new `backend/app/templates.py` + routes)
- `TEMPLATES: list[dict]` (the table above) and `THEMES: list[dict]` ({id, label, tags}).
- `GET /templates` → `{templates, themes}` (Card-free; small static payload).
- `POST /deck/theme-suggest?limit=10&offset=0` body `{commander_id, themes: [id], free_text}`
  → `{cards: [{card, score, themes_matched}], total, has_more}`. Algorithm:
  1. pool = union of `_tag_inverted[tag]` for each tag in each selected theme (+ free-text matches).
  2. filter: color_identity ⊆ commander CI; not basic; not in `BANLIST`; has IER.
  3. per card: `ier_norm = min(ier/20, 1)`; `syn` = commander EDHREC synergy (clamp 0–1) if the
     commander has EDHREC rows, else structural synergy of (commander, card) via `synergy_neighbors`.
     `relevance = 1.0 + 0.5*(themes_matched − 1)` (1.5× for cards bridging both themes).
     `score = relevance * (0.5*ier_norm + 0.5*syn)`.
  4. sort desc, tiebreak card_id; paginate `[offset:offset+limit]`; `has_more = offset+limit < total`.
- `models.py`: `DeckRequest` gains optional `template: dict[str,int] | None = None`. `/deck/complete`
  passes `req.template or doctor.TEMPLATE` into `complete_deck(...)` (it already takes `template`).
- New models: `TemplateInfo`, `ThemeInfo`, `ThemeSuggestion`, `ThemeSuggestResponse`.
- Tests (`backend/tests/test_templates.py`): GET /templates shape; theme-suggest returns in-CI
  non-basic cards ordered by score desc; pagination (offset/has_more); both-theme cards get the
  1.5× boost; bad commander → 400. Reuse the real store like test_suggest.py.

## Frontend (frontend-design skill drives the visuals)
- `lib/types.ts`: `TemplateInfo`, `ThemeInfo`, `ThemeSuggestion`, `ThemeSuggestResponse`.
- `lib/api.ts`: `getTemplates()`, `themeSuggest(commanderId, themes, freeText, limit, offset)`.
- `store/template.ts` (zustand): `{templates, themes, selectedId, composite:{counts, themeA, themeB,
  freeText}, activeCounts()}` — `activeCounts()` returns the selected template's counts (composite
  returns its edited counts). page.tsx passes `activeCounts()` into `DeckDoctorPanel` →
  `postDeckComplete(entries, commanderId, activeCounts())`.
- **Header dropdown** "Template ▾" near the existing header buttons. Changing it sets `selectedId`
  (and thus the Doctor quotas). Selecting Composite opens the panel.
- `components/TemplatePanel.tsx` (right panel, copy SuggestionsPanel chrome): composition bars
  (target count per category, with current deck count overlaid); for the Composite: **two columns**
  Theme A / Theme B, each a theme `<select>` + a free-text `<input>`; below, the **theme card grid**
  (10+ `CardTile`s, badge = efficiency, ordered best→least), and a **"Show 10 more"** button at the
  bottom that bumps `offset` (react-query keyed on commander+themes+freeText+limit).
- Aesthetic note (frontend-design): the app's existing theme is dark jewel panels + amber arabesque
  (`accent`/`panel`/`edge`/`ink`, Cinzel display font). Keep that language; make the Composite's
  dual-theme columns feel like two facing "spell pages" (gilded divider down the middle), and the
  card grid reveal with a short staggered fade. Don't introduce a new font/palette — match the deck.

## Verification gate (Playwright)
Header dropdown lists all 6 templates → pick Control → Doctor "Complete" fills toward 13 removal /
6 wipes (counts shift vs Command Zone). Pick Simmander Composite → two theme columns appear → choose
Aristocrats + Card Draw → 10 cards load, ordered by efficiency, all within commander colors → "Show
10 more" appends 10 → cards bridging both themes rank near the top.

## Status notes for whoever resumes
- Spellbook crawl is COMPLETE (91,196 variants → 87,980 combos live). Backend + frontend dev servers
  may still be running from this session (:8001 / :3000) — kill by port-owner PID before restarting.
- All SP1–SP11 shipped; 43 backend + 92 scoring tests green. This template feature is the only open work.
