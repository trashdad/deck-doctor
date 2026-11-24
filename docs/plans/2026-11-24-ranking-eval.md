# Ranking eval: cut_to_100 and the pivot finder (2026-11-24)

Status: **done**. Code: `tools/eval/` (`backtest_cuts.py`, `backtest_pivot.py`, `common.py`,
`test_eval_helpers.py`). Raw results: `tools/eval/results/*.json` (seed 20261124, DB
`deckdoctor_test`, read-only; each JSON records sha256 prefixes of the ranking code it ran).

## Why

`cut_to_100.py` ranked cuts with `ROLE_W = 0.15`, `CURVE_W = 0.10`; `pivot.py` scored
commanders with `0.5 / 0.3 / 0.2 / 1.0`. Nobody had measured them. This doc records an
offline backtest, a train-only grid search with a pre-registered selection rule, and the
held-out result.

## Prior art (what the design borrows)

- **Intruder / odd-one-out tests.** Chang, Boyd-Graber et al., *Reading Tea Leaves: How
  Humans Interpret Topic Models* (NeurIPS 2009,
  https://papers.nips.cc/paper/2009/hash/f92586a25bb3145facd64ab20fd554ff-Abstract.html):
  plant a word that does not belong among a topic's words and test whether it is found.
  "Which card should go" is the same question about a deck, so we plant known-bad cards
  in real decks and measure whether the ranker picks them.
- **Injected anomalies, by type.** ADBench (Han et al., NeurIPS 2022 Datasets & Benchmarks,
  https://arxiv.org/abs/2206.09426) evaluates detectors on real and synthetic anomalies
  and reports results per anomaly type. We report recall per intruder type (random /
  off-curve / role glut) instead of one blended number.
- **Rank everything; don't sample.** Krichene & Rendle, *On Sampled Metrics for Item
  Recommendation* (KDD 2020, https://research.google/pubs/on-sampled-metrics-for-item-recommendation/)
  show that metrics computed over sampled candidates can disagree with exact ones. Both
  backtests rank the full candidate set (every card in the deck, every commander with an
  EDHREC page).
- **Leave-out replay** (hide something real, ask the system to recover it) is the standard
  offline recommender test. The pivot backtest hides the deck's own commander and asks
  for it back. `scoring/eval_suggest.py` already does this for the suggester.

## Data

- Corpus: `data/decks.sqlite`, 5,263 scraped decks. Eligible decks: the commander
  resolves to a legal commander with an EDHREC page, at least 95 % of the card names
  resolve, and there are 60–99 distinct non-commander cards (the corpus collapses
  basics). Identical lists are kept once. That leaves 4,307 decks across 204 commanders.
- Sample: 600 decks, seeded, at most 5 per commander so a few popular commanders cannot
  dominate.
- Split: **commander-disjoint**, using crc32 of the commander name: 70 % train
  (389 decks) and 30 % held-out (211 decks). No held-out commander's decks, EDHREC page
  or intruders are seen during tuning.
- **Leakage caveat.** The co-occurrence table and the EDHREC pages were built from, or
  alongside, these same decks. Absolute numbers are optimistic, so use them only to
  compare weight settings on the same decks.

## 1. cut_to_100: injected-intruder backtest (`backtest_cuts.py`)

**Design.** Each sampled deck is padded back to 99 with basics of the commander's colours
(the corpus stores each card name once). Then k ∈ [3, 8] known-bad cards are planted
(seeded per deck), so the deck is 99 + k + commander and over 100 by exactly k.
`cut_to_100` runs through its normal `target=None` path. Each planted card is non-land,
in colour identity, not banned, not already in the deck, and **off-theme**: fewer than
10 % of this commander's EDHREC decks run it. Each one has one of three types:

- `random`: any such card.
- `curve`: such a card with cmc ≥ 7.
- `role_glut`: such a card in a quota role the deck already fills (a 4th board wipe if
  the deck has ≥ 3; otherwise the most over-full role).

There are two pools for drawing the planted cards:

- **played**: 3,597 cards found in the corpus co-occurrence table. These are plausible
  cards that someone actually plays.
- **legal**: 30,318 castable cards. Most of these carry no corpus signal, like a deck's
  obscure picks.

**Metrics.**

- `recall@k`: share of the k cuts that are planted cards. Cuts = k, so this equals
  precision.
- Per-type recall.
- `damage@X`: cuts of *original* cards that ≥ X of the commander's EDHREC decks run,
  divided by k. This is the "cut a card everybody plays" failure.

**Selection rule** (fixed before looking at held-out data). On train, take the best
recall@k among settings whose damage@0.5 is no worse than (0.15, 0.10)'s. Then apply the
one-standard-error rule: from the settings within 1 SE of that best, pick the one closest
to (0.15, 0.10). Grid: ROLE_W × CURVE_W ∈ {0, .05, .1, .15, .2, .3, .5, .75, 1}².

**Held-out results** (211 decks, commanders never seen in tuning; random-cut reference
recall 0.053):

| pool | setting | recall@k | random | curve | role_glut | damage@0.5 |
|---|---|---|---|---|---|---|
| played | **invented 0.15 / 0.10** | **0.312** | 0.188 | 0.204 | 0.591 | **0.021** |
| played | pure weakness 0 / 0 | 0.231 | 0.183 | 0.256 | 0.290 | 0.075 |
| legal | **invented 0.15 / 0.10** | **0.395** | 0.310 | 0.252 | 0.677 | **0.015** |
| legal | pure weakness 0 / 0 | 0.452 | 0.486 | 0.429 | 0.492 | 0.068 |
| legal | per-regime rule pick 0.05 / 0.05 | 0.438 | 0.373 | 0.322 | 0.672 | 0.016 |

Paired bootstrap on held-out decks, 95 % CI:

- **played**: invented − pure recall **+0.081** [+0.051, +0.109]; damage@0.5 **−0.054**
  [−0.075, −0.033].
- **legal**: invented − pure recall **−0.057** [−0.093, −0.020]; damage@0.5 −0.053
  [−0.074, −0.034].
- **legal**: (0.05, 0.05) − invented recall +0.043 [+0.028, +0.058]; damage +0.0005
  [−0.006, +0.006].

**What this shows.**

1. The role and curve terms are not decoration. They roughly double recall on
   role-glut intruders (a 4th wipe, surplus ramp): 0.29 → 0.59 played, 0.49 → 0.68
   legal. They also cut **3.5–4.4× fewer staples of the commander** in both regimes.
2. They cost recall on *random obscure* intruders. Many real deck cards score exactly 0
   on suggest_cuts' contribution, because they have no EDHREC row, no co-occurrence and
   no staple signal. A random obscure card ties with them, and the role/curve terms then
   push surplus-role cards ahead of it. The intruder type decides whether the terms help
   or hurt overall recall.
3. The two regimes pick different weights. The per-regime rule keeps (0.15, 0.10) on
   `played` but picks (0.05, 0.05) on `legal`. On the `played` train split, (0.05, 0.05)
   has lower recall (0.330 vs 0.334) and more damage (0.0126 vs 0.0104).
   `combine_cuts.py` therefore checks both regimes on **train only**. A setting is
   admissible if its damage@0.5 is within 0.002 of invented's in both regimes, and
   admissible settings are ranked by mean recall. The best is (0.20, 0.10) at 0.372 vs
   0.369 for (0.15, 0.10): a +0.003 difference, well inside one SE (~0.012 per regime). This rule was
   added after the two regimes disagreed; it is disclosed here and uses train data only.

**Decision.** Keep `ROLE_W = 0.15`, `CURVE_W = 0.10`. They now sit on the measured
recall/damage frontier instead of being invented. No change is supported. Whether a
lower role weight would serve real users better depends on whether real bad cards look
more like `played` or like `legal` intruders: **UNKNOWN** from this data. The bigger
lever is the 0-contribution floor in `suggest_cuts` (doctor.py, not owned here). Many
obscure but intended cards score exactly 0, so their cut order is decided by card-id
tie-breaks and the role/curve terms.

## 2. Pivot finder: replay backtest (`backtest_pivot.py`)

**Design.**

- **Own-commander recovery.** Drop commander A from a real deck of A. Then
  `find_pivots(None, deck)` ranks all 354 commanders with EDHREC pages; measure the rank
  of A. A scorer that cannot find a deck's own commander is unlikely to rank
  alternatives well. Two variants:
  - full deck;
  - **partial**: 30 random non-basic cards, a deck in progress. This variant is harder,
    so the weights are tuned on it.
- **Neighbour surfacing.** For each deck, find the corpus deck with the highest Jaccard
  overlap that was built on a different commander B. If Jaccard ≥ 0.4 (top ~8 %; the
  median nearest overlap is 0.21), B is a real alternative. Measure B's rank with A
  excluded, which is what the UI shows when A is the current commander. Only 50 of 600
  decks qualify (21 held-out).
- The script re-scores with `pivot.pivot_score`, the production formula, now factored
  out. It asserts that, at production weights, its order equals `find_pivots`' order on
  every run (1,200 runs: identical).

**Selection rule.** On train, take the best partial MRR among settings whose full-deck
MRR is no worse than invented's. Then apply the 1-SE rule toward the invented weights.
Grid: 594 points (coverage {0, .25, .5, 1} × inclusion {0, .15, .3, .6, 1} × synergy
{0, .1, .2, .4, .8} × off-colour {0, .25, .5, 1, 2, 4}).

**Held-out results** (211 decks; neighbour n = 21):

| setting (cov, inc, syn, off) | full MRR | full hit@1 | partial MRR | partial hit@1 | partial hit@10 | neighbour MRR | neighbour hit@10 |
|---|---|---|---|---|---|---|---|
| **invented 0.5, 0.3, 0.2, 1** (= rule's pick) | **0.912** | 0.863 | **0.895** | 0.844 | 0.991 | 0.627 | 0.952 |
| coverage only | 0.924 | 0.882 | 0.880 | 0.829 | 0.981 | 0.590 | 0.952 |
| inclusion only | 0.881 | 0.815 | 0.827 | 0.749 | 0.972 | 0.548 | 0.952 |

The train partial MRR ranges from 0.506 to 0.891 across the grid. The best train
settings drop the synergy term (0.891 vs 0.882 invented, SE 0.013), which is within one
SE. The rule therefore keeps the invented weights, and the held-out bootstrap difference
is exactly 0.

**What this shows.**

- The blend clearly beats inclusion-only.
- It beats coverage-only on partial decks (0.895 vs 0.880). Coverage-only is slightly
  ahead on full decks (0.924 vs 0.912).
- The metric is near its ceiling on full decks (hit@10 = 0.99). Weights inside a broad
  region are indistinguishable.
- W_OFF_COLOR is barely tested: the true commander never has off-colour cards, and train
  partial MRR moves only from 0.871 to 0.883 across 0–4.
- The neighbour metric (n = 21 held-out, SE ≈ 0.08) is too small to separate settings:
  **UNKNOWN**.

**Decision.** Keep (0.5, 0.3, 0.2, 1.0). No grid point beats them outside the noise.
W_OFF_COLOR stays a policy choice (how hard to penalise forced cuts), not a measured one.

## Code changes

- `backend/app/cut_to_100.py`: `cut_to_100(..., role_w=None, curve_w=None)` overrides
  (None means the module constants). The constants are unchanged, and their comment
  cites this doc.
- `backend/app/pivot.py`:
  - `WEIGHTS` tuple.
  - `pivot_score()`: the single formula used by `score_commander` and the backtest.
  - `score_commander(..., weights=None)`.
  - The constants are unchanged, and their comment cites this doc.
- Tests:
  - `test_cut_to_100.py` +2: weight override and module-constant defaults.
  - `test_pivot.py` +1: `pivot_score` blend and override.
  - `tools/eval/test_eval_helpers.py` (5): split, bootstrap, the rank tie-break that
    matches `find_pivots`, and both selection rules.

## Reproduce

```
export DATABASE_URL=postgresql://deckdoctor@localhost/deckdoctor_test   # read-only use
python -I tools/eval/backtest_cuts.py --pool played     # ~2.5 min -> results/cuts_played.json
python -I tools/eval/backtest_cuts.py --pool legal      # ~3.5 min -> results/cuts_legal.json
python -I tools/eval/combine_cuts.py                    # train-only cross-regime table
python -I tools/eval/backtest_pivot.py                  # ~1 min   -> results/pivot.json
```

Defaults are 600 decks and seed 20261124. Re-runs gave identical numbers. Results depend
on the working-tree `category_of` (doctor.py now also treats any mana ability as ramp),
recorded in each JSON's `code_sha256_12`.
