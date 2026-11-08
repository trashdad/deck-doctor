"use client";

import { createContext, useContext } from "react";
import type { ActionDeps } from "./cardActions";

/** The per-page half of ActionDeps (stores); CardInteractive adds zone/why per card. */
export type PageActionDeps = Omit<ActionDeps, "zone" | "why">;

const noop = () => {};

/** Safe default so a CardInteractive outside a provider still renders a menu. */
export const NOOP_ACTION_DEPS: PageActionDeps = {
  deck: { add: noop, remove: noop, move: noop, setCommander: noop },
  cuts: { toggle: noop, has: () => false },
  explorer: noop,
  semantic: noop,
  upgrade: noop,
  commanders: [],
};

const Ctx = createContext<PageActionDeps>(NOOP_ACTION_DEPS);

export function CardActionsProvider({ deps, children }: { deps: PageActionDeps; children: React.ReactNode }) {
  return <Ctx.Provider value={deps}>{children}</Ctx.Provider>;
}

export function useCardActionDeps(): PageActionDeps {
  return useContext(Ctx);
}
