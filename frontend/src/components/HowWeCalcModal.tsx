"use client";

import { useEffect } from "react";

/**
 * "HOW WE CALC": a plain-language overlay explaining how Deck Doctor rates
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
        className="flex max-h-[88vh] w-full max-w-3xl flex-col rounded-2xl border border-accent/50 bg-ink/90 shadow-neon backdrop-blur-md"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-accent/30 px-6 py-4">
          <div>
            <p className="arcade-bevel text-sm">How We Calc</p>
            <p className="text-[11px] uppercase tracking-widest text-zinc-500">
              What&apos;s actually behind the numbers
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-zinc-500 transition hover:bg-accent/10 hover:text-accent"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="space-y-5 overflow-y-auto px-6 py-5 text-[13px] leading-relaxed text-zinc-300 scrollbar-thin">
          <section className="rounded-lg border border-accent/30 bg-accent/5 p-4">
            <p>
              <span className="font-semibold text-accent">Short version:</span> we worked out all the
              numbers before you ever showed up. There&apos;s a mountain of real Magic data behind this
              thing, and we chew through it in the background and write the answers down. By the time
              you&apos;re dropping cards on the board, the site isn&apos;t calculating anything. It&apos;s
              reading what we already figured out. That&apos;s why it&apos;s fast, and why it runs fine on
              your phone.
            </p>
          </section>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">
              What efficiency actually means
            </h3>
            <p className="mb-2">
              An efficiency number answers one thing: what a card gives you back versus what it costs to
              play it.
            </p>
            <p className="mb-2">
              Every card is a trade. You spend mana, usually a card out of your hand too, and you get
              something for it. More cards, a body on the board, a dead removal spell, some damage, a bit of
              ramp. When the payoff is clearly bigger than the price, the card scores well. When you&apos;re
              overpaying for a small effect, it doesn&apos;t.
            </p>
            <p className="mb-2">
              We weigh up the whole card and drop the result onto one scale, so a one-mana rock and a
              six-mana bomb sit side by side and you can actually compare them.
            </p>
            <p>A couple of things people get wrong about this number:</p>
            <ul className="mt-1.5 space-y-1.5 pl-1">
              <li className="flex gap-2">
                <span className="text-accent">•</span>
                <span>
                  It rates the card on its own, with zero knowledge of your deck. Plenty of high-scoring
                  cards are completely wrong for what you&apos;re building, and plenty of low-scoring ones
                  are the exact glue your deck needs.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-accent">•</span>
                <span>
                  We don&apos;t rank suggestions by it. It&apos;s one input, not the answer. Mostly it sits
                  there to break ties and tell you a card&apos;s ceiling at a glance.
                </span>
              </li>
            </ul>
          </div>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">
              How we pick cards for you
            </h3>
            <p className="mb-2">
              Rating power and picking the right card are two different jobs. For the second one we read
              your card pool four ways at once.
            </p>
            <p className="mb-2">
              First, is the card any good on its own? That&apos;s the efficiency score, a quick sanity
              check so we&apos;re not handing you junk.
            </p>
            <p className="mb-2">
              Second, and this is the big one: do real decks actually run these cards together? We&apos;ve
              been through thousands of decklists that real people built and played. When two cards keep
              turning up in the same deck far more than chance would explain, that&apos;s everyone who plays
              the format telling us they belong together. We lean on that hard. It came from real games, not
              from somebody&apos;s opinion.
            </p>
            <p className="mb-2">
              Third, are two cards just doing the same job? We track which cards are swappable. The five
              &ldquo;destroy target creature&rdquo; spells, the pile of mana rocks, the draw engines that
              all do roughly the same thing. That keeps us from offering you eight versions of one effect,
              and it lets us suggest real swaps.
            </p>
            <p className="mb-2">
              Fourth, do any of these cards go off together? We check your pool against a big catalog of
              known combos and interactions. If you&apos;re one card short of a wincon, you should hear it
              from us.
            </p>
            <p>
              Then we mix those four together and weight the whole thing by your commander and what&apos;s
              already on the board. A card that&apos;s strong, shows up in decks like yours, covers a job
              you&apos;re missing, and plays nice with your other cards floats to the top. One that only
              manages a single one of those doesn&apos;t.
            </p>
          </div>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">
              Where this all comes from
            </h3>
            <p className="mb-2">We didn&apos;t make any of it up. It&apos;s built on:</p>
            <ul className="mb-2 space-y-1.5 pl-1">
              <li className="flex gap-2">
                <span className="text-accent">•</span>
                <span>a big pile of real decklists, and it keeps growing</span>
              </li>
              <li className="flex gap-2">
                <span className="text-accent">•</span>
                <span>format-wide stats on what gets played with which commanders</span>
              </li>
              <li className="flex gap-2">
                <span className="text-accent">•</span>
                <span>a hand-checked catalog of combos</span>
              </li>
            </ul>
            <p>
              We pull that in, scrub it, and keep it current, so the advice doesn&apos;t go stale. New sets
              land, the format moves, the patterns shift with it, and your recommendations get a little
              sharper on their own.
            </p>
          </div>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">
              Why nothing&apos;s &ldquo;thinking&rdquo; when you click
            </h3>
            <p className="mb-2">
              The reason this feels instant is that the slow part already happened. Working out how every
              card relates to every other card is a mountain of math, so we run it offline, once, and save
              the results. The live site never touches that math again. You add a card, it grabs the numbers
              it needs and blends a few of them right there.
            </p>
            <p>
              So you get an answer immediately, it works on a phone, and it doesn&apos;t cost a fortune to
              keep running. We just did the homework early.
            </p>
          </div>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">
              Finishing a deck, and trimming one down
            </h3>
            <p className="mb-2">
              When you hit &ldquo;complete my deck,&rdquo; we&apos;re not jamming in the most powerful cards
              we can find. We fill toward a shape that actually works: enough lands, ramp, draw, removal,
              wipes, the usual. For each open slot we grab the card that does the most for the cards
              you&apos;ve already got, using that same four-way read.
            </p>
            <p>
              Cuts run backwards. We take what&apos;s already in the deck and rank it by how little each card
              is doing for the rest, then put the weakest stuff in front of you so you can call it.
            </p>
          </div>

          <div>
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">Your lands</h3>
            <p>
              Lands get the same treatment. We start from the fixing and utility lands that real decks in
              your colors actually run, duals included, with a price cap if you want to keep it cheap. Then
              we fill the rest with basics in the right amounts for the colors your deck leans on, instead of
              splitting them evenly and calling it a day. The point is a mana base that casts your spells.
            </p>
          </div>

          <div className="rounded-lg border border-cyan/30 bg-cyan/5 p-4">
            <h3 className="mb-1.5 font-display text-base font-semibold text-accent">One honest note</h3>
            <p>
              This is a strong starting point and a good second opinion. It&apos;s read more decklists than
              you ever could and it remembers all of them. But it&apos;s showing you the consensus, so it
              plays it safe sometimes. The weird, personal, deck-defining picks are still on you. You build
              the deck. We just make sure you don&apos;t miss an obvious synergy, a combo you&apos;re one
              card away from, or some dead weight you should&apos;ve cut ages ago.
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
