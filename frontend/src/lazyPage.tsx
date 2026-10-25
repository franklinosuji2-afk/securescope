import { Suspense, lazy, type ComponentType } from "react";
import { Loading } from "./components/ui";

/** Shown instead of a page whose code could not be loaded. This happens when a new version was released
 * while the tab was open: the old file names no longer exist. It never reloads by itself. */
export function StalePage() {
  return (
    <div className="card" role="alert">
      <h1>This page could not be loaded</h1>
      <p>
        SecureScope was probably updated while this tab was open. Reload to get
        the new version; nothing you saved is lost.
      </p>
      <button
        type="button"
        className="btn"
        onClick={() => window.location.reload()}
      >
        Reload
      </button>
    </div>
  );
}

/** Loads a page when it is first opened. A failed load shows `StalePage` instead of an empty screen. */
export function lazyPage<T extends ComponentType<any>>( // eslint-disable-line @typescript-eslint/no-explicit-any
  load: () => Promise<{ default: T }>,
) {
  return lazy(() =>
    load().catch(() => ({ default: StalePage as unknown as T })),
  );
}

export function PageLoader({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<Loading label="Loading…" />}>{children}</Suspense>
  );
}
