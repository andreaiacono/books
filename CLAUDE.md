# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

**BiblioTrack** — a fully static personal library manager + reading diary. No backend, no build step, hosted on GitHub Pages. All persistence is done via the GitHub Contents API directly from the browser.

## Development

No build toolchain. Serve locally with:

```bash
python3 -m http.server 8000
```

No linting, no tests, no package.json.

## Architecture

### Data flow

1. On page load, `js/data.js` fetches `data/grid.json` (lightweight catalog) and `data/reading-log.csv` (reading diary).
2. They are joined by ISBN in `getEnrichedCatalog()` → enriched book objects used by all views.
3. Per-book detail (`data/books/{isbn}.json`) is lazy-loaded only when `book.html` is opened.
4. `js/search.js` builds a Lunr.js index over the enriched catalog.
5. `js/ui.js` provides shared rendering: `renderBookCard()`, `buildFilterBar()`, `applyFilterSort()`, toast notifications, loading overlay.

### Search behaviour (`js/search.js`)

- Stemming is **enabled** (default Lunr pipeline).
- Plain queries automatically apply **fuzzy matching (edit distance 2)** and **trailing wildcard** per term via `_index.query()`, so partial or approximate terms match.
- Queries containing Lunr syntax characters (`:`, `"`, `~`, `^`, `+`, `-`, `*`) bypass the automatic expansion and pass directly to `_index.search()`.
- Field weights: title (10) > author (5) > subjects (3) > year/publisher/description (1).

### "Add book" flow (`add.html`)

1. User enters an ISBN; `fetchISBNMetadata()` tries Open Library first, then Google Books.
2. Cover is fetched via `allorigins.win` CORS proxy and converted to base64.
3. `saveNewBook()` commits three files to GitHub via the API: cover webp, detail JSON, updated `grid.json`.
4. GitHub credentials (PAT + repo + branch) stored only in `localStorage`, configured via `settings.html`.

### Key data formats

- `data/grid.json` — `[{isbn, title, author, year, cover}]` — loaded at startup by every page.
- `data/books/{isbn}.json` — full metadata per book, lazy loaded on `book.html`.
- `data/reading-log.csv` — columns: `date,title,comment,creators,isbn,marked`; date format `DD/MM/YYYY`.
- Covers stored as `covers/{isbn}.webp`.

### CDN dependencies (no npm)

- **PapaParse 5.4** — CSV parsing
- **Lunr.js 2.3** — full-text search
- Google Fonts — Playfair Display, DM Sans, DM Mono

All loaded via `<script>` tags; JS modules use native ES `import`/`export`.

### PWA

`manifest.json` + `sw.js` make the app installable and offline-capable after first load. `assets/sw-register.html` is a snippet included in pages to register the service worker.