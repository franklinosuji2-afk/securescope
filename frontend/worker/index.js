// Cloudflare Worker entry. Static files are served by Cloudflare's asset layer; only /api/* reaches this code
// (see run_worker_first in wrangler.jsonc). It forwards API calls to the backend so the browser only ever talks
// to one origin (cookies and CSRF keep working) and tells the backend the visitor's real address, proven by a
// shared secret, so rate limits apply per visitor instead of to this proxy.
//
// Settings (Worker > Settings > Variables and Secrets, type Secret):
//   BACKEND_URL   e.g. https://securescope-api.onrender.com   (no trailing slash)
//   PROXY_SECRET  a long random string; the backend gets the same value as SECURESCOPE_TRUSTED_PROXY_SECRET
//   CRON_SECRET   (optional) at least 32 random characters; the backend gets the same value as
//                 SECURESCOPE_CRON_SECRET. Without it the scheduled trigger does nothing, so scheduled scans are off.
//
// A cron trigger (wrangler.jsonc) wakes the backend every 15 minutes and asks it to run the scans that are due.
// That endpoint is never reachable through the public proxy below.

export default {
  async fetch(request, env) {
    if (!env.BACKEND_URL || !env.PROXY_SECRET) {
      return new Response(
        JSON.stringify({ detail: "The API is not configured." }),
        {
          status: 503,
          headers: {
            "content-type": "application/json",
            "cache-control": "no-store",
          },
        },
      );
    }
    const incoming = new URL(request.url);
    // Internal endpoints are for the cron trigger only, which calls the backend directly.
    if (incoming.pathname.startsWith("/api/v1/internal")) {
      return new Response(JSON.stringify({ detail: "Not found." }), {
        status: 404,
        headers: {
          "content-type": "application/json",
          "cache-control": "no-store",
        },
      });
    }
    const target = new URL(
      incoming.pathname + incoming.search,
      env.BACKEND_URL,
    );
    const headers = new Headers(request.headers);
    // Never trust these from a visitor: overwrite them.
    headers.delete("x-proxy-secret");
    headers.delete("x-real-client-ip");
    headers.delete("x-forwarded-for");
    headers.set("x-proxy-secret", env.PROXY_SECRET);
    const visitor = request.headers.get("cf-connecting-ip");
    if (visitor) headers.set("x-real-client-ip", visitor);
    const init = {
      method: request.method,
      headers,
      body: request.body,
      redirect: "manual",
    };
    // Streaming a request body needs duplex "half" outside Cloudflare's runtime; Cloudflare ignores it.
    if (request.body) init.duplex = "half";
    return fetch(new Request(target, init));
  },

  // Cron trigger: ask the backend to run the scheduled scans that are due.
  async scheduled(_controller, env, ctx) {
    if (!env.BACKEND_URL || !env.CRON_SECRET) return;
    const target = new URL("/api/v1/internal/run-due", env.BACKEND_URL);
    ctx.waitUntil(
      fetch(
        new Request(target, {
          method: "POST",
          headers: { "x-cron-secret": env.CRON_SECRET },
          // A sleeping free-tier backend needs about a minute to wake, and the scans themselves take a while.
          signal: AbortSignal.timeout(170000),
        }),
      ).catch(() => undefined),
    );
  },
};
