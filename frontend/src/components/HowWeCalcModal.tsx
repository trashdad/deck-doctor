"use client";

import { useEffect } from "react";

/**
 * "HOW WE CALC" — a plain-language overlay explaining how Deck Doctor rates
 * efficiency and makes its recommendations. Process, not formulas.
 */
export function HowWeCalcModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[170] flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
      data-testid="how-we-calc"
    >
      <div
        className="flex max-h-[88vh] w-full max-w-3xl flex-col rounded-2xl border border-accent/50 bg-panel shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-accent/30 px-6 py-4">
          <div>
            <p className="font-display text-lg font-bold tracking-wide text-accent">How We Calc</p>
            <p className="text-[11px] uppercase tracking-widest text-zinc-500">
              How Deck Doctor rates cards &amp; makes its calls
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-zinc-500 transition hover:bg-zinc-700 hover:text-zinc-200"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="space-y-5 overflow-y-auto px-6 py-5 text-[13px] leading-relaxed text-zinc-300 scrollbar-thin">
          <section className="rounded-lg border border-accent/30 bg-accent/5 p-4">
            <p>
              <span className="font-semibold text-accent">The 30-second version.</span> Every number you
              see in Deck Doctor was figured out <em>ahead of time</em>. We read a giant pile of real
              Magic data once, in the background, and boil it down into simple &ldquo;index cards&rdquo;
              of pre-chewed answers. So when you drop a card onto the board, the site isn&apos;t
              thinking &mdash; it&apos;s <em>looking up</em> what it already worked out. That&apos;s why
              it answers in a blink, and why it doesn&apos;t need a supercomputer to do it.
            </p>
          </section>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">
              What &ldquo;efficiency&rdquo; really measures
            </h3>
            <p className="mb-2">
              When we put an efficiency number on a card, we&apos;re asking one question:{" "}
              <strong className="text-zinc-100">
                how much does this card give you back compared to what it costs you?
              </strong>
            </p>
            <p className="mb-2">
              Every card is a trade. You pay mana &mdash; and usually a card out of your hand &mdash; and
              you get something in return: more cards, a creature on the board, a problem removed, damage,
              ramp, protection. A card is <em>efficient</em> when the stuff you get clearly outweighs the
              price you paid, and <em>inefficient</em> when you overpay for a small effect.
            </p>
            <p className="mb-2">
              So we look at the whole picture of a card &mdash; what it costs, how much board presence or
              card advantage it generates, how big or impactful it is, and how quickly it pays you back
              &mdash; and put all of that onto <strong className="text-zinc-100">one shared scale</strong>.
              That lets you line up a one-mana rock next to a six-mana bomb and actually compare them
              fairly.
            </p>
            <p>Two things worth keeping in mind:</p>
            <ul className="mt-1.5 space-y-1.5 pl-1">
              <li className="flex gap-2">
                <span className="text-accent">•</span>
                <span>
                  It&apos;s an <strong className="text-zinc-100">&ldquo;in a vacuum&rdquo; rating</strong>{" "}
                  &mdash; how strong the card is on its own, before we know anything about <em>your</em>{" "}
                  deck. A card can be wildly efficient and still be wrong for you, and a humble-looking
                  card can be the perfect glue for your strategy.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-accent">•</span>
                <span>
                  It&apos;s deliberately <strong className="text-zinc-100">not</strong> the thing we use to
                  rank suggestions. Raw power is one ingredient, not the whole recipe. It mostly shows up
                  to break ties and give you a gut sense of a card&apos;s ceiling.
                </span>
              </li>
            </ul>
          </div>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">
              How we decide what to recommend
            </h3>
            <p className="mb-2">
              Picking the <em>right</em> card for your deck is a different job than rating raw power. We
              look at your card pool through <strong className="text-zinc-100">four lenses at once</strong>,
              because no single one tells the whole story:
            </p>
            <ol className="space-y-2.5">
              <li>
                <span className="font-semibold text-zinc-100">1. Is the card strong on its own?</span>{" "}
                That&apos;s the efficiency rating above &mdash; a sanity check that we&apos;re not
                suggesting junk.
              </li>
              <li>
                <span className="font-semibold text-zinc-100">
                  2. Do real decks actually run these cards together?
                </span>{" "}
                This is the heart of it. We&apos;ve studied thousands of real, human-built decklists. When
                two cards show up <em>together</em> far more often than random chance would explain,
                that&apos;s the community quietly telling us they belong in the same deck. We trust that
                signal a lot, because it&apos;s earned from real games, not guessed.
              </li>
              <li>
                <span className="font-semibold text-zinc-100">
                  3. Are two cards basically doing the same job?
                </span>{" "}
                We map out which cards are <em>interchangeable</em> &mdash; the five different
                &ldquo;destroy target creature&rdquo; spells, the dozen mana rocks, the redundant draw
                engines. Knowing this lets us suggest real swaps, avoid handing you eight versions of the
                same effect, and understand the <em>role</em> each card plays.
              </li>
              <li>
                <span className="font-semibold text-zinc-100">
                  4. Do these cards combine into something bigger?
                </span>{" "}
                We cross-reference a big, curated catalog of known card interactions and combos. If your
                deck is one piece away from a finisher, we want to be the one to point it out.
              </li>
            </ol>
            <p className="mt-2">
              Then we <strong className="text-zinc-100">blend those four lenses together</strong>, weighted
              by your commander and everything already on your board. A card that&apos;s powerful, beloved
              by decks like yours, fills a role you&apos;re missing, <em>and</em> plays nicely with what
              you&apos;ve got is going to rise to the top. Something that only checks one box won&apos;t.
            </p>
          </div>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">
              Where the knowledge comes from
            </h3>
            <p className="mb-2">
              None of this is invented. It all traces back to{" "}
              <strong className="text-zinc-100">real human play</strong>:
            </p>
            <ul className="mb-2 space-y-1.5 pl-1">
              <li className="flex gap-2">
                <span className="text-accent">•</span>
                <span>A large, constantly-growing library of actual decklists people have built and played.</span>
              </li>
              <li className="flex gap-2">
                <span className="text-accent">•</span>
                <span>Community-wide statistics about what gets played with which commanders.</span>
              </li>
              <li className="flex gap-2">
                <span className="text-accent">•</span>
                <span>A curated catalog of known combos and interactions.</span>
              </li>
            </ul>
            <p>
              We pull that data in, clean it up, and keep it fresh &mdash; which means the advice
              isn&apos;t frozen in time. As the format shifts and new cards land, the patterns update, and
              your recommendations quietly get smarter without you doing a thing.
            </p>
          </div>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">
              Why there&apos;s no &ldquo;AI&rdquo; thinking when you click
            </h3>
            <p className="mb-2">
              Here&apos;s the trick that makes the whole thing feel instant:{" "}
              <strong className="text-zinc-100">we do the expensive thinking offline, ahead of time.</strong>{" "}
              Figuring out how every card relates to every other card is an enormous amount of work &mdash;
              so we do it in the background, once, and write the conclusions down. The live website never
              re-does that math. When you add a card, it just reads the relevant pre-computed numbers and
              blends a few of them on the spot.
            </p>
            <p>
              That&apos;s why answers come back in the blink of an eye, why it works on a phone, and why it
              doesn&apos;t cost a fortune to run. The genius isn&apos;t a giant brain answering each
              question &mdash; it&apos;s having already done the homework.
            </p>
          </div>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">
              Completing your deck, and trimming it
            </h3>
            <p className="mb-2">
              When you ask the Doctor to <strong className="text-zinc-100">complete your deck</strong>,
              we&apos;re not stuffing it with the most powerful cards we can find. We&apos;re filling it
              toward a <em>sensible shape</em> &mdash; enough lands, ramp, card draw, removal, board wipes,
              and so on &mdash; and for each slot we pick the card that pulls the most weight alongside what
              you already have, using those same four lenses.
            </p>
            <p>
              When you ask for <strong className="text-zinc-100">cuts</strong>, we flip it around: we rank
              the cards already in your deck by how <em>little</em> they&apos;re contributing to everything
              else, and surface the weakest links so you can decide what to trim.
            </p>
          </div>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">Building your manabase</h3>
            <p>
              Lands get the same treatment. When you fill your lands, we start from the fixing and utility
              lands that <em>real decks in your colors actually run</em> &mdash; dual lands included, with
              an optional price cap so you can keep it on budget &mdash; and then round the rest out with
              basics matched to your deck&apos;s real color demands, not just an even split. The goal is a
              mana base that actually casts your spells, not a pretty pile of off-color lands.
            </p>
          </div>

          <div className="rounded-lg border border-edge bg-zinc-900/40 p-4">
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">The honest part</h3>
            <p>
              Deck Doctor is a sharp <strong className="text-zinc-100">starting point and a second
              opinion</strong> &mdash; a tireless librarian who has read more decklists than any human ever
              could and remembers all of them. But it&apos;s reflecting the <em>consensus</em> of what
              people play, so it can lean a little safe and conventional. The spicy, deck-defining choices?
              That&apos;s still you. You&apos;re the deckbuilder. We just make sure you never miss an obvious
              synergy, a one-card-away combo, or a piece of dead weight that should&apos;ve been cut.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end border-t border-accent/30 px-6 py-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-accent/50 bg-accent/10 px-4 py-1.5 text-xs font-semibold
                       text-accent transition hover:bg-accent/25"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
