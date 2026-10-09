/* Slim service worker for the Pilote Budget PWA.
 *
 * Strategy:
 * - Never cache /api/* responses (financial data stays out of the cache).
 * - Navigations: network-first, falling back to the cached app shell so the
 *   installed app keeps opening when the phone is offline.
 * - Everything else (hashed assets, icons, manifest): stale-while-revalidate.
 *
 * A fresh Vite build hashes asset filenames, so bumping CACHE_VERSION at
 * deploy time invalidaates stale entry points automatically.
 */
"use strict";

const CACHE_VERSION = "pilote-v1";
const SHELL_URL = "/index.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_VERSION)
      .then((cache) => cache.add(SHELL_URL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

function isNavigationRequest(request) {
  return request.mode === "navigate";
}

async function handleFetch(request) {
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return fetch(request);
  }

  // Never serve or store API payloads from the cache.
  if (url.pathname.startsWith("/api/")) {
    return fetch(request);
  }

  const cache = await caches.open(CACHE_VERSION);

  if (isNavigationRequest(request)) {
    try {
      const network = await fetch(request);
      if (network.ok) cache.put(SHELL_URL, network.clone());
      return network;
    } catch (error) {
      const fallback = await cache.match(SHELL_URL);
      if (fallback) return fallback;
      throw error;
    }
  }

  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached);
  return cached || networkPromise;
}

self.addEventListener("fetch", (event) => {
  event.respondWith(handleFetch(event.request));
});