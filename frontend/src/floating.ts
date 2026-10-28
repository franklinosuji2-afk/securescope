/**
 * Floating cards. Cards that lift on hover also lean slightly toward the pointer and show a soft light under it.
 * This only publishes the pointer position as CSS variables (--px, --py, --rx, --ry) on the card under the mouse;
 * the look is defined in motion.css, which also switches it off for people who prefer reduced motion.
 */

/** Cards that float. Keep this in step with the hover rules at the end of motion.css. */
export const FLOATING_CARDS = [
  ".landing .card",
  ".landing .sample-notice",
  ".landing-sample",
  ".landing-numbers > div",
  ".landing-steps > li",
  ".summary-card",
  ".bento-card",
].join(",");

/** The most a card turns toward the pointer, in degrees. Small on purpose. */
const MAX_TILT = 2.5;

const VARIABLES = ["--px", "--py", "--rx", "--ry"] as const;

function clear(card: HTMLElement): void {
  for (const name of VARIABLES) card.style.removeProperty(name);
}

/** Starts listening. Returns a function that stops. Does nothing on touch-only devices. */
export function initFloatingCards(): () => void {
  if (
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function" ||
    !window.matchMedia("(hover: hover) and (pointer: fine)").matches
  ) {
    return () => undefined;
  }

  let frame = 0;
  let pending: { card: HTMLElement; x: number; y: number } | null = null;
  let active: HTMLElement | null = null;

  const flush = () => {
    frame = 0;
    if (!pending) return;
    const { card, x, y } = pending;
    pending = null;
    const box = card.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) return;
    const px = Math.min(1, Math.max(0, (x - box.left) / box.width));
    const py = Math.min(1, Math.max(0, (y - box.top) / box.height));
    card.style.setProperty("--px", `${(px * 100).toFixed(1)}%`);
    card.style.setProperty("--py", `${(py * 100).toFixed(1)}%`);
    card.style.setProperty(
      "--rx",
      `${((px - 0.5) * 2 * MAX_TILT).toFixed(2)}deg`,
    );
    card.style.setProperty(
      "--ry",
      `${((0.5 - py) * 2 * MAX_TILT).toFixed(2)}deg`,
    );
  };

  const onMove = (event: PointerEvent) => {
    if (event.pointerType !== "mouse") return;
    const target = event.target instanceof Element ? event.target : null;
    const card = target?.closest<HTMLElement>(FLOATING_CARDS) ?? null;
    if (active && active !== card) clear(active);
    active = card;
    if (!card) return;
    pending = { card, x: event.clientX, y: event.clientY };
    if (!frame) frame = window.requestAnimationFrame(flush);
  };

  const onLeave = (event: MouseEvent) => {
    if (!active) return;
    const next =
      event.relatedTarget instanceof Node ? event.relatedTarget : null;
    if (next && active.contains(next)) return;
    clear(active);
    active = null;
  };

  document.addEventListener("pointermove", onMove, { passive: true });
  document.addEventListener("mouseout", onLeave, { passive: true });
  return () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("mouseout", onLeave);
    if (frame) window.cancelAnimationFrame(frame);
    if (active) clear(active);
  };
}
