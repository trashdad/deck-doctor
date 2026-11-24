# Draft: permission request to EDHREC

**Status: DRAFT — not sent.** The owner reviews, fills the placeholders, confirms every
statement is still true, and sends it personally. Context and evidence:
`docs/plans/2026-11-24-edhrec-compliance.md`.

Before sending, check:

- [ ] The two product facts in the last paragraph are still accurate (Patreon gate scope; the
      ManaPool / TCGplayer affiliate links).
- [ ] You are willing to make the commitment in the "If the answer is no" paragraph.
- [ ] Keep or delete the bracketed OPTIONAL licence-fee clause.
- [ ] Whether to stop the EDHREC signal in production (`DECKDOCTOR_EDHREC_SIGNAL=off`) before
      sending, so "I have stopped" is literally true. As drafted, the email says the requests are
      stopped, which is true once the scraper change is deployed; the stored numbers are still used
      until the switch is off.

---

**To:** contact@edhrec.com
**Subject:** Permission request: using EDHREC inclusion and synergy data in a free Commander deckbuilder

Hello EDHREC team,

My name is [YOUR NAME]. I build Deck Doctor, a free Commander deckbuilder at
https://simmander.app/deck-doctor. Its source code is public at
https://github.com/trashdad/deck-doctor.

I owe you a straight account first. Deck Doctor has been ranking card suggestions partly with
per-commander inclusion and synergy figures from EDHREC. A script in that repository requested
`json.edhrec.com` commander pages and `edhrec.com` deck-preview responses, and stored the results.
I have now read your Terms of Use (effective August 6, 2024) and `https://edhrec.com/robots.txt`,
which disallows `/deckpreview/`. I have disabled that script, and I have added a switch that runs
the site without any EDHREC data.

I would like to ask whether Space Cow Media would allow one of the following for Deck Doctor:

1. A data licence or feed you prefer, limited to per-commander card inclusion and synergy, with
   the attribution wording and link you specify; or
2. Written permission to keep a local copy of those two fields and show them in the tool with a
   credit and a link to the commander's EDHREC page.

I am happy to accept limits on refresh frequency, the commanders covered, or anything else that
works for you[OPTIONAL — keep only if true: , and to discuss a licence fee if that is how you
handle requests like this].

If the answer is no, I will delete the stored EDHREC metrics and the saved deck-preview responses
and keep the tool running without that signal. Please also tell me if you want earlier copies
removed from the public repository's history.

So you have the full picture: card recommendations in Deck Doctor are free to use. An optional
Patreon subscription unlocks a breakdown of Deck Doctor's own card-efficiency score; it does not
gate card names, card images or suggestions. Card pages show ManaPool and TCGplayer buy links,
which can carry affiliate codes.

Thank you for EDHREC and for reading this.

Best regards,
[YOUR NAME]
[REPLY EMAIL ADDRESS]
Deck Doctor — https://simmander.app/deck-doctor
