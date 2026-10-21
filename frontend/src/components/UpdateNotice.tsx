import { useEffect, useState } from "react";
import { newVersionAvailable } from "../updateCheck";

const CHECK_EVERY_MS = 15 * 60 * 1000;

/** Shown when a newer version was released while this tab was open. It never reloads by itself, so nothing
 * a person is typing is lost. */
export default function UpdateNotice() {
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    let stopped = false;
    async function check() {
      if (stopped || document.visibilityState === "hidden") return;
      if (await newVersionAvailable()) {
        if (!stopped) setAvailable(true);
      }
    }
    const timer = window.setInterval(() => void check(), CHECK_EVERY_MS);
    const onVisible = () => void check();
    document.addEventListener("visibilitychange", onVisible);
    void check();
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  if (!available) return null;
  return (
    <div className="update-notice" role="status">
      <span>A new version of SecureScope is available.</span>
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
