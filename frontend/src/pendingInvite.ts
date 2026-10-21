/**
 * An invitation link opened while signed out has to survive the sign-in (which can leave the site for
 * Google or GitHub and come back). The token waits in this tab's session storage until the person is
 * signed in, then the app takes them back to the invitation. Storage can be unavailable, so every use is guarded.
 */
const KEY = "securescope.invite";

export function rememberInvite(token: string): void {
  try {
    window.sessionStorage.setItem(KEY, token);
  } catch {
    /* the link in the email still works */
  }
}

export function pendingInvite(): string | null {
  try {
    const token = window.sessionStorage.getItem(KEY);
    return token && /^[A-Za-z0-9_-]{10,200}$/.test(token) ? token : null;
  } catch {
    return null;
  }
}

export function forgetInvite(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* nothing to clear */
  }
}
