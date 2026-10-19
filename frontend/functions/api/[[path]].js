// Cloudflare Pages Function: forwards /api/* to the backend so the browser only ever talks to one
// origin (cookies and CSRF keep working). It also tells the backend the visitor's real address, proven by
// a shared secret, so rate limits apply per visitor instead of to this proxy.
//
// Settings (Pages project > Settings > Variables and Secrets):
//   BACKEND_URL   e.g. https://securescope-api.onrender.com   (no trailing slash)
//   PROXY_SECRET  a long random string; the backend gets the same value as SECURESCOPE_TRUSTED_PROXY_SECRET

export async function onRequest({ request, env }) {
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
  const target = new URL(incoming.pathname + incoming.search, env.BACKEND_URL);
  const headers = new Headers(request.headers);
  // Never trust these from a visitor: overwrite them.
  headers.delete("x-proxy-secret");
  headers.delete("x-real-client-ip");
  headers.delete("x-forwarded-for");
  headers.set("x-proxy-secret", env.PROXY_SECRET);
  const visitor = request.headers.get("cf-connecting-ip");
  if (visitor) headers.set("x-real-client-ip", visitor);
  return fetch(
    new Request(target, {
      method: request.method,
      headers,
      body: request.body,
      redirect: "manual",
    }),
  );
}
