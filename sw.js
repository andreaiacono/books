// sw.js — BiblioTrack Service Worker

const CACHE_NAME = 'bibliotrack-v1';
const CACHE_SHELL = [
  '/',
  '/index.html',
  '/search.html',
  '/reading-log.html',
  '/add.html',
  '/book.html',
  '/settings.html',
  '/css/style.css',
  '/js/data.js',
  '/js/search.js',
  '/js/ui.js',
  '/assets/no-cover.svg',
  '/assets/icon.svg',
  'https://cdnjs.cloudflare.com/ajax/libs/PapaParse/5.4.1/papaparse.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/lunr.js/2.3.9/lunr.min.js',
];

// Data files: cache on first fetch, serve stale while revalidating
const DATA_PATTERNS = [
  /\/data\/grid\.json/,
  /\/data\/reading-log\.csv/,
  /\/data\/books\//,
];

// Covers: cache-first (images don't change once written)
const COVER_PATTERN = /\/covers\//;

// ─── Install ──────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(CACHE_SHELL))
      .then(() => self.skipWaiting())
  );
});

// ─── Activate ─────────────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// ─── Fetch ────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const url = event.request.url;

  // Don't intercept GitHub API calls or external metadata APIs
  if (url.includes('api.github.com') ||
      url.includes('openlibrary.org') ||
      url.includes('googleapis.com') ||
      url.includes('allorigins.win')) {
    return;
  }

  // Covers: cache-first
  if (COVER_PATTERN.test(url)) {
    event.respondWith(cacheFirst(event.request));
    return;
  }

  // Data files: stale-while-revalidate
  if (DATA_PATTERNS.some(p => p.test(url))) {
    event.respondWith(staleWhileRevalidate(event.request));
    return;
  }

  // App shell: cache-first
  event.respondWith(cacheFirst(event.request));
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Offline', { status: 503 });
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request).then(response => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  }).catch(() => null);

  return cached ?? fetchPromise;
}
