import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthProvider } from "./auth";
import UpdateNotice from "./components/UpdateNotice";
import { initFloatingCards } from "./floating";
import "@fontsource-variable/inter/wght.css";
import "@fontsource-variable/plus-jakarta-sans/wght.css";
import "./styles.css";
import "./bento.css";
import "./dashboard.css";
import "./motion.css";

// Links from emails look like /reset-password?token=... or /accept-invite?token=... ; the app uses hash routes.
const emailLink = /^\/(reset-password|verify-email|accept-invite)$/.exec(
  window.location.pathname,
);
if (emailLink) {
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  window.history.replaceState(
    null,
    "",
    `/#/${emailLink[1]}?token=${encodeURIComponent(token)}`,
  );
}

initFloatingCards();

const container = document.getElementById("root");
if (!container) throw new Error("Root element missing");
createRoot(container).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
    {import.meta.env.PROD && <UpdateNotice />}
  </StrictMode>,
);

// Lets phones install the app. Only in production builds, so development never serves stale files.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}
