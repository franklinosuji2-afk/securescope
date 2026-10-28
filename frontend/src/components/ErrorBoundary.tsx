import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** "page" keeps the menu and replaces only the page; "app" replaces everything. */
  scope: "page" | "app";
}

/** Catches a failure while drawing a page (for example a server answer in a shape the page did not expect) so
 * one bad response cannot blank the whole app. It shows a fixed message: the error itself is never shown to
 * the person, and nothing is sent anywhere. Callers reset it by changing its `key`. */
export default class ErrorBoundary extends Component<
  Props,
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("A page failed to render.", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    const body = (
      <div className="card empty" role="alert">
        <h1>This page could not be shown</h1>
        <p>
          Something went wrong while drawing it. Nothing you saved is lost.
          Reload to try again, or <a href="#/">go to the start page</a>.
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
    return this.props.scope === "app" ? (
      <main id="main" className="auth-wrap">
        {body}
      </main>
    ) : (
      body
    );
  }
}
