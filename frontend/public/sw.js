// Minimal service worker so the app can be installed and opens quickly.
// It caches only the static app shell. It never touches /api, so no account data is ever stored offline.
const CACHE = "securescope-shell-v2";
// Fixed files only. The page itself ("/") is stored after each successful visit, never frozen here, so
// the offline copy is always the version that was last online.
const SHELL = [
  "/favicon.svg",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api/")
  )
    return;
  if (request.mode === "navigate") {
    // Always try the network first so a new release is picked up; keep the latest page for offline use.
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put("/", copy));
          }
          return response;
        })
        .catch(() => caches.match("/")),
    );
    return;
  }
  // Only built assets (hashed names, so safe to keep) and the fixed shell files are served from the cache.
  // Everything else, including a script asking for "/", goes to the network.
  const cacheable =
    url.pathname.startsWith("/assets/") || SHELL.includes(url.pathname);
  if (!cacheable) return;
  event.respondWith(
    caches.match(request).then(
      (hit) =>
        hit ||
        fetch(request).then((response) => {
          if (response.ok && url.pathname.startsWith("/assets/")) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        }),
    ),
  );
});
