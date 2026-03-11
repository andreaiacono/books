# MyBooks

A fully static personal library manager + reading diary. No backend. No build step. Hosted on GitHub Pages.

---

## Features

- **Library grid** — cover thumbnails with read/favourite badges, grouped by month read, with filter & sort
- **Stats bar** — total books, read, unread, and favourites at a glance
- **Full-text search** — Lunr.js index with field weights (title > author > subjects > description)
- **Book detail** — metadata, subjects, reading record, link to Google Books, inline "add reading entry" form
- **Reading log** — your existing CSV diary, enriched with covers from the catalog, grouped by year/month and collapsible
- **Add book** — type an ISBN, metadata is fetched from Open Library / Google Books automatically, cover downloaded, everything committed to GitHub via the API — entirely in the browser
- **Light/dark theme** — toggle with system preference detection
- **PWA** — installable, works offline after first load

---

## Repository structure

```
/
├── index.html           Library grid
├── search.html          Search
├── reading-log.html     Reading diary
├── add.html             Add book via ISBN
├── book.html            Book detail
├── settings.html        GitHub PAT configuration
├── manifest.json        PWA manifest
├── sw.js                Service worker
├── css/
│   └── style.css
├── js/
│   ├── data.js          Data layer (load, join, GitHub API writes)
│   ├── search.js        Lunr search index
│   ├── theme.js         Light/dark theme toggle
│   └── ui.js            Shared rendering utilities
├── data/
│   ├── grid.json        [{isbn, title, author, year, cover}]  ← loaded at startup
│   ├── reading-log.csv  Your reading diary (existing format, untouched)
│   └── books/
│       └── {isbn}.json  Full metadata per book (lazy loaded)
├── covers/
│   └── {isbn}.webp      Book cover images
└── assets/
    ├── no-cover.svg
    └── icon.svg
```

---

## Initial setup

### 1. Fork / create the repository

Create a new GitHub repository and enable GitHub Pages (Settings → Pages → Deploy from branch: `main`, folder: `/`).

### 2. Import your existing books

You have two options:

**Option A — batch ISBN import script** (recommended for large collections):
```bash
node tools/import.js < my-isbns.txt
```
*(A simple Node helper that calls Open Library for each ISBN and generates the JSON files — see `tools/import.js`.)*

**Option B — add books one by one** via the Add Book page in the app.

### 3. Configure GitHub in the app

1. Open **Settings** in the app
2. Enter your repository name (e.g. `alice/my-library`)
3. Create a PAT at [github.com/settings/tokens](https://github.com/settings/tokens) with scope `public_repo`
4. Paste the PAT into Settings and click Save

The token is stored only in your browser's `localStorage` and is never committed to the repo.

---

## Data formats

### `data/grid.json`
```json
[
  {
    "isbn": "9780141033570",
    "title": "Thinking, Fast and Slow",
    "author": "Daniel Kahneman",
    "year": 2011,
    "cover": "covers/9780141033570.webp"
  }
]
```

### `data/books/{isbn}.json`
```json
{
  "isbn": "9780141033570",
  "title": "Thinking, Fast and Slow",
  "author": "Daniel Kahneman",
  "year": 2011,
  "cover": "covers/9780141033570.webp",
  "publisher": "Penguin",
  "pages": 499,
  "language": "en",
  "description": "...",
  "subjects": ["Psychology", "Decision making"],
  "source": "openlibrary",
  "addedAt": "2025-03-05T10:00:00Z"
}
```

### `data/reading-log.csv`
Your existing file — unchanged format:
```
date,title,comment,creators,isbn,marked
14/11/2022,Thinking Fast and Slow,fondamentale.,Daniel Kahneman,9780141033570,true
```

---

## How the join works

At runtime the app loads both `grid.json` and `reading-log.csv`, then joins them by ISBN:

```
catalog book  +  reading log entry  →  enriched book
(what you own)   (when you read it)    (shown in grid with ✓ badge)
```

Books in the catalog but not the log → shown without read badge.
Books in the log but not the catalog (borrowed, ebooks, etc.) → shown in Reading Log only.
~5% of log entries without ISBNs stay unlinked but appear in the log view.

---

## Search syntax (Lunr)

| Query | Meaning |
|---|---|
| `borges` | fuzzy match (edit distance 1) + wildcard across all fields |
| `author:borges` | author field only |
| `title:"magic realism"` | exact phrase in title |
| `borges -argentina` | borges, excluding argentina |
| `sci*` | wildcard |

Plain queries automatically apply fuzzy matching (edit distance 1) and a trailing wildcard per term. Queries containing Lunr syntax characters (`:`, `"`, `~`, `^`, `+`, `-`, `*`) are passed through directly to the Lunr engine.

---

## Dependencies (CDN only)

- [PapaParse 5.4](https://www.papaparse.com/) — CSV parsing
- [Lunr.js 2.3](https://lunrjs.com/) — full-text search
- Google Fonts — Playfair Display + DM Sans + DM Mono

No build toolchain required.
