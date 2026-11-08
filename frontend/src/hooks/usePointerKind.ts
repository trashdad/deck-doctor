"use client";

import { useSyncExternalStore } from "react";

/** Last input modality the user touched the page with. */
export type PointerKind = "mouse" | "pen" | "touch" | "keyboard";

let kind: PointerKind = "mouse";
const subs = new Set<() => void>();
let installed = false;

function setKind(k: PointerKind) {
  if (k === kind) return;
  kind = k;
  subs.forEach((fn) => fn());
}

const NAV_KEYS = new Set([
  "Tab",
  "ArrowUp",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "Enter",
  " ",
  "Escape",
  "Home",
  "End",
  "F10",
  "ContextMenu",
]);

function install() {
  if (installed || typeof window === "undefined") return;
  installed = true;
  window.addEventListener(
    "pointerdown",
    (e) => {
      const t = e.pointerType;
      setKind(t === "touch" ? "touch" : t === "pen" ? "pen" : "mouse");
    },
    { capture: true, passive: true },
  );
  // Hover alone counts as mouse/pen (a pen hovers too).
  window.addEventListener(
    "pointermove",
    (e) => {
      if (e.pointerType === "mouse") setKind("mouse");
      else if (e.pointerType === "pen") setKind("pen");
    },
    { capture: true, passive: true },
  );
  window.addEventListener(
    "touchstart",
    () => setKind("touch"),
    { capture: true, passive: true },
  );
  window.addEventListener(
    "keydown",
    (e) => {
      if (NAV_KEYS.has(e.key)) setKind("keyboard");
    },
    { capture: true },
  );
}

/** Non-hook accessor for event handlers and stores. */
export function getPointerKind(): PointerKind {
  install();
  return kind;
}

function subscribe(fn: () => void) {
  install();
  subs.add(fn);
  return () => {
    subs.delete(fn);
  };
}

export function usePointerKind(): PointerKind {
  return useSyncExternalStore(subscribe, () => kind, () => "mouse");
}

/** True when the device's primary input cannot hover (phones, tablets). */
export function isCoarsePointer(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(hover: none), (pointer: coarse)").matches;
}
