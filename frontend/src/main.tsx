import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthProvider } from "./auth";
import "./styles.css";

// Links from emails look like /reset-password?token=... ; the app uses hash routes.
const emailLink = /^\/(reset-password|verify-email)$/.exec(window.location.pathname);
if (emailLink) {
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  window.history.replaceState(null, "", `/#/${emailLink[1]}?token=${encodeURIComponent(token)}`);
}

const container = document.getElementById("root");
if (!container) throw new Error("Root element missing");
createRoot(container).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>,
);
