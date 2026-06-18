/**
 * Helpers for detecting the cross-origin iframe context.
 *
 * The Replit preview pane and the canvas embed the terminal inside a
 * cross-origin proxied iframe. Chrome's Web Speech recognition and
 * `getUserMedia` microphone capture are blocked in cross-origin frames unless
 * the parent delegates `allow="microphone"`, which these embeds do not. So
 * Voice Mode can never reach the mic there — we detect this up front and offer
 * an "open in a new tab" escape hatch instead of silently failing.
 */
export function isEmbedded(): boolean {
  if (typeof window === "undefined") return false;
  let differentWindow = false;
  try {
    differentWindow = window.self !== window.top;
  } catch {
    // Accessing window.top threw → we're inside a cross-origin frame.
    return true;
  }
  if (!differentWindow) return false;
  // We're in an iframe; determine whether it's cross-origin. Reading the
  // parent's origin throws when cross-origin (which is exactly the blocked case).
  try {
    return window.top!.location.origin !== window.location.origin;
  } catch {
    return true;
  }
}

/** Open the current app URL in a standalone top-level browser tab. */
export function openStandaloneTab(): Window | null {
  if (typeof window === "undefined") return null;
  return window.open(window.location.href, "_blank", "noopener,noreferrer");
}
