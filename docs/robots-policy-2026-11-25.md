# Robots.txt policy (2026-11-25)

## Current stance

- **We do not currently follow robots.txt.** Ignoring robots.txt is **only for
  testing and development purposes**, and robots.txt **will be respected in the
  future**.
- Instead of relying on robots.txt, **we contact each website individually and
  work with them directly** — asking for permission, recording the person who
  granted it, the date, and any rate limit they set. That record lives in
  `tools/scrape_decklists/permissions.json` (machine-read by the scraper) with
  the saved replies under `docs/permissions/`.
- Sites we are working with:
  - **EDHREC** — permission on file: `docs/permissions/edhrec-2026-11-24.md`
  - **Archidekt** — permission on file: `docs/permissions/archidekt-2026-11-24.md`
  - **Moxfield** — permission on file: `docs/permissions/moxfield-2026-11-24.md`
  - **TappedOut** — verbal permission (John Smith, Investor Relations; written
    email confirmation pending): `docs/permissions/tappedout-2026-11-25.md`
- Sites not yet contacted (stay paused until they are): Deckstats, AetherHub,
  ManaStack.

## Why

Robots.txt is a machine convention, not an agreement with the site operators.
A direct relationship is stronger on both sides: the site names its own
comfortable rate (e.g. Archidekt: 1 request / 20 s; TappedOut: 1 request /
30 s), and we know exactly who to talk to if anything changes. The scraper's
per-host throttle can only go slower than a granted rate, never faster.

## Future

Robots.txt will be respected once testing and development are complete.
