# What Commander players want from deckbuilding tools: research summary

*Research run 2026-11-03. Sources: public forum discussion (Jun 2025 to Nov 2026), plus app-store reviews, forums, changelogs and social posts. Individual authors are not identified and quotes are paraphrased.*

## 1. Headline finding

Players do not lack card lists. They lack a tool that understands their own deck. Most complaints about current tools boil down to this: the tool reports what other people play, not what this particular deck needs.

- EDHREC is valued as an on-ramp and a "did I forget a card?" check, but distrusted as a recommender. Commenters (one at score 116) said it aggregates inclusion, not performance.
- Moxfield wins because decks live there: sharing, speed and habit. It is not praised for advice.
- Generic AI advice is actively disliked (invented cards, illegal color identity), so trust is the adoption gate for any new recommender.

The open ground is a deterministic, explainable second opinion on a deck the player already has. It says why, never invents a card, and respects color identity, budget, collection and power target.

## 2. What players like

| Theme | Where seen | Implication |
|---|---|---|
| A link anyone can open | Moxfield, ManaBox | Sharing and import are the real moat; people will not rebuild dozens of decks for a new tool. |
| Speed and a clean editor | Moxfield, Archidekt | Builder speed is fragile; a mobile layout change prompted threats to leave. |
| Seeing a deck as roles (ramp, draw, removal, curve) | Archidekt categories, Scryfall tags | Roles match how brewers think. |
| EDHREC as on-ramp and sanity check | EDHREC | The problem is blind use of popularity data, not the data itself. |
| Scryfall search and tags | Scryfall | Loved by experts; the syntax is a barrier for others. |
| Combo lookup with prerequisites | Commander Spellbook | Trusted because it is human-curated and shows steps. |
| Solo playtesting before buying | Archidekt, Moxfield | Real need, but table stakes. |
| Scan a pile to CSV | ManaBox | Collection input is considered solved. |

## 3. What players dislike (ranked by frequency and intensity)

1. Popularity presented as advice: staples first, a feedback loop of copying, sameness. Some EDHREC contributors have acknowledged this publicly.
2. Precon pollution: unmodified precon lists skew recommendation data. This was the highest-scoring concrete complaint in the corpus (score 214).
3. Advice that ignores the deck's plan, such as suggesting a premium rock for a low-curve aggro list, or cutting ramp spells in a deck with a cheap commander.
4. Generic AI output: invented cards, wrong rules text, off-color suggestions. The strongest objections target opaque "bracket check" or "vibe check" apps, not automation in principle.
5. Bracket and power estimates that misfire; one card or a two-card loop can jump a deck a bracket, and Bracket 3 spans a very wide range. Players asked for finer granularity.
6. Needing several tools for one hobby (deck site, scanner, combo site, bracket site), with imports that break on proxies, foils and printings.
7. Ads, paywalled basics, mobile as an afterthought, outages.
8. Solitaire goldfishing with no opposition.

## 4. Unmet needs, ordered by evidence strength and how directly they block a core job

| # | Need | Evidence | Software can fix? |
|---|---|---|---|
| 1 | Suggestions that follow this deck (plan, curve, commander speed) rather than the commander's average list | Very strong | Yes |
| 2 | Filter precon-origin noise from recommendation data; precon-aware tune-ups, including the alternate commander | Strong; highest single score | Yes |
| 3 | "What do I cut?" to reach 100, aware of roles and curve | Strong | Yes |
| 4 | Trustable, explainable analysis that never invents cards and shows why | Strong; the adoption gate | Yes |
| 5 | Find cards by effect rather than popularity or search syntax | Strong | Yes |
| 6 | Commander pivot: which commander reuses most of my 99 | Strong in posts; no tool named | Yes |
| 7 | Finer, less "vibes-based" bracket placement | Strong but diffuse | Partly; the social half is not software |
| 8 | Recommendations constrained to my colors, budget and collection | Medium to strong | Yes, needs collection input |
| 9 | Nonbo and rules-trap warnings on recommended cards | Medium | Yes |
| 10 | Combos one card away, with honest prerequisites | Medium | Mostly solved by existing tools |

Areas that look large but were judged poor bets: Rule 0 and pod-expectation tooling (real pain, but no one named software that fixes it), multiplayer simulators, scanners, price or cart optimizers, in-game companions. Each is crowded or social.

Broader communities also supported two points. Collection-first brewing ("build from what I own") has real demand and is stronger outside the main Commander forum than within it. Many players said they dislike cutting cards, which supports a cut-to-100 focus. AI branding is a positioning liability, so lead with "explains why, never invents a card" rather than the word "AI".

## 5. Candidate directions and design implications

- **A. Deck-specific second opinion (recommended).** Precon-clean data and alternate-commander-aware tune-ups; cut-to-100 that respects roles and curve with a one-line reason per card; a commander pivot finder; plus a trust layer (deterministic, never invents a card, color-identity-safe, nonbo-aware).
- **B. Import-first wedge.** Make pasting a list the whole onboarding. Likely a prerequisite to A rather than a separate product. URL import feasibility is UNKNOWN.
- **C. Power-level honesty.** Highest raw pain but diffuse and half social, with incumbents already present. Treat as a feature of A, shown as a floor ("at least Bracket N, because of these flags"), never a bare verdict.
- **D. Collection-first.** Real demand, different product shape. Offer "only cards I own" as a constraint option on A, and revisit if casual players matter more than the evidence suggests.

Do not build: another deck editor, a playtester, a scanner, or a social/Rule 0 tool.

Resulting UX principles from the plan:
- The deck stays visible; advice lives in a persistent side rail, not a covering drawer.
- Every suggestion is a plain sentence of reasoning, with numbers shown as supporting evidence after it.
- Show the source of each recommendation (popularity, real decks, mechanics, combo, staple) and offer a "hide staples" toggle.
- Show role counts against a template and a deck-count pill ("N over, cut to 100").
- Bracket is displayed as a floor with the flags that set it.
- Never render a card the data does not contain; filter off-color cards.
- State data provenance honestly, including card-data date and whether precon cleaning was done (only after it is verified).
- Hover to preview, right-click or long-press to act, with keyboard and touch parity; a real stacked mobile layout.
- Casual-table players are UNKNOWN in the evidence, so the first design targets experienced Commander players.

Suggested positioning line: the second opinion for the deck you have already built; it tells you what is weak in this list, what to cut and why, and what to add, without just handing you the commander's most popular cards and without ever making a card up.

## 6. Methods and limits

- **Corpus.** Public forum posts and comments from Jun 2025 to Nov 2026, plus non-forum sources (app stores, forums, changelogs, social posts). Total number of posts: UNKNOWN. Comments: top 1,500 most-discussed threads mentioning a product, about 112k comments, up to 300 per thread. A separate post-only slice of three broader communities covered 668 posts (91% of cited quotes verified); only one post came from the casual-play community in that slice. A separate recommendation-data corpus of about 85k decks is referenced for follow-up tests.
- **Analysis.** Three independent LLM analyses (posts, comments, comments) plus one on non-forum sources converged on the same cluster of needs. Quotes were checked against raw text by ID. Verified share was 89 to 99% for the stronger analysis files, 61% and 67% for two weaker files; those two were used for themes only. Non-forum quotes were not independently re-verified.
- **Counts are not prevalence.** Slices were selected by keyword, so cluster sizes overstate how common a need is (the bracket slice is deliberately over-represented). Use the ordering, not the percentages.
- **Selection bias.** Forum users skew toward vocal, advanced players; the main Commander forum is about 97% of the comment evidence. Newcomers and casual-table players are under-represented. Product-specific forums were small, and some product communities returned nothing.
- **No usage or purchase data.** Stated pain is not willingness to adopt. Statements that a finding "validates" an existing feature are analyst inference, not tested.
- **Suggested next tests.** (1) A precon-noise audit on the deck corpus; (2) a read-only hand review of cut-to-100 output on about 20 real over-sized lists; (3) post the positioning line with a screenshot and see what people ask for.

## Redaction notes

- Removed all usernames, comment and post IDs, scores tied to a specific comment (kept only the two aggregate scores 116 and 214), links and thread titles.
- Replaced every verbatim quote with a paraphrase; none exceed a few words.
- Removed the names of individual EDHREC writers and of a user-built third-party tool, referring to them generically.
- Dropped the analysis file names, internal code paths, branch names and owner-specific working notes from the plan.
- Counts and percentages were copied from the source documents; the total post count is not stated there and is marked UNKNOWN.
