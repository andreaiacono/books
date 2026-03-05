// js/data.js — Data layer: loads, caches, and joins all data sources

const DATA = {
  grid: null,        // [{isbn, title, author, year, cover}]
  readMap: null,     // Map<isbn, readingLogEntry>
  detailCache: {},   // isbn -> detail object (lazy loaded)
};

// ─── Loaders ────────────────────────────────────────────────────────────────

export async function loadGrid() {
  if (DATA.grid) return DATA.grid;
  const res = await fetch('data/grid.json');
  if (!res.ok) throw new Error('Could not load grid.json');
  DATA.grid = await res.json();
  return DATA.grid;
}

export async function loadReadingLog() {
  if (DATA.readMap) return DATA.readMap;
  const res = await fetch('data/reading-log.csv');
  if (!res.ok) { DATA.readMap = new Map(); return DATA.readMap; }
  const text = await res.text();
  const parsed = Papa.parse(text, { header: true, skipEmptyLines: true });
  DATA.readMap = new Map();
  for (const row of parsed.data) {
    if (row.isbn && row.isbn.trim()) {
      DATA.readMap.set(row.isbn.trim(), {
        dateFinished: row.date?.trim() ?? null,
        comment:      row.comment?.trim() ?? null,
        marked:       row.marked?.trim() === 'true',
      });
    }
  }
  return DATA.readMap;
}

export async function loadBookDetail(isbn) {
  if (DATA.detailCache[isbn]) return DATA.detailCache[isbn];
  try {
    const res = await fetch(`data/books/${isbn}.json`);
    if (!res.ok) return null;
    DATA.detailCache[isbn] = await res.json();
    return DATA.detailCache[isbn];
  } catch { return null; }
}

// ─── Enriched catalog ───────────────────────────────────────────────────────

export async function getEnrichedCatalog() {
  const [grid, readMap] = await Promise.all([loadGrid(), loadReadingLog()]);
  return grid.map(book => ({
    ...book,
    reading: readMap.get(book.isbn) ?? null,
  }));
}

// ─── GitHub API persistence ─────────────────────────────────────────────────

const GITHUB_API = 'https://api.github.com';

function getConfig() {
  return {
    token: localStorage.getItem('gh_token'),
    repo:  localStorage.getItem('gh_repo'),   // e.g. "username/my-library"
    branch: localStorage.getItem('gh_branch') ?? 'main',
  };
}

export function isConfigured() {
  const { token, repo } = getConfig();
  return !!(token && repo);
}

async function ghGet(path) {
  const { token, repo } = getConfig();
  const res = await fetch(`${GITHUB_API}/repos/${repo}/contents/${path}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
  });
  if (!res.ok) throw new Error(`GitHub GET failed: ${res.status} ${path}`);
  return res.json();
}

async function ghPut(path, content /* base64 */, sha, message) {
  const { token, repo, branch } = getConfig();
  const res = await fetch(`${GITHUB_API}/repos/${repo}/contents/${path}`, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, content, sha, branch }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(`GitHub PUT failed: ${res.status} — ${err.message ?? path}`);
  }
  return res.json();
}

// ─── Book persistence ───────────────────────────────────────────────────────

export async function saveNewBook(book, detailObj, coverBase64, coverMime) {
  // book:       {isbn, title, author, year, cover}
  // detailObj:  full metadata object
  // coverBase64: raw base64 string (or null to skip)
  // coverMime:  e.g. 'image/webp'

  const steps = [];

  // 1. Upload cover if provided
  if (coverBase64) {
    const coverPath = `covers/${book.isbn}.webp`;
    let coverSha;
    try { const f = await ghGet(coverPath); coverSha = f.sha; } catch { /* new file */ }
    await ghPut(coverPath, coverBase64, coverSha, `cover: ${book.isbn}`);
    steps.push('cover');
  }

  // 2. Write detail JSON
  const detailPath = `data/books/${book.isbn}.json`;
  let detailSha;
  try { const f = await ghGet(detailPath); detailSha = f.sha; } catch { /* new */ }
  const detailContent = btoa(unescape(encodeURIComponent(JSON.stringify(detailObj, null, 2))));
  await ghPut(detailPath, detailContent, detailSha, `detail: ${book.title}`);
  steps.push('detail');

  // 3. Update grid.json
  const gridFile = await ghGet('data/grid.json');
  const currentGrid = JSON.parse(decodeURIComponent(escape(atob(gridFile.content.replace(/\n/g, '')))));
  const alreadyExists = currentGrid.findIndex(b => b.isbn === book.isbn);
  if (alreadyExists >= 0) currentGrid[alreadyExists] = book;
  else currentGrid.push(book);
  const gridContent = btoa(unescape(encodeURIComponent(JSON.stringify(currentGrid, null, 2))));
  await ghPut('data/grid.json', gridContent, gridFile.sha, `add: ${book.title}`);
  steps.push('grid');

  // Update local cache
  if (DATA.grid) {
    const idx = DATA.grid.findIndex(b => b.isbn === book.isbn);
    if (idx >= 0) DATA.grid[idx] = book; else DATA.grid.push(book);
  }
  DATA.detailCache[book.isbn] = detailObj;

  return steps;
}

// ─── ISBN metadata fetch ─────────────────────────────────────────────────────

export async function fetchISBNMetadata(isbn) {
  // Try Open Library first
  try {
    const res = await fetch(`https://openlibrary.org/api/books?bibkeys=ISBN:${isbn}&jscmd=data&format=json`);
    const data = await res.json();
    const key = `ISBN:${isbn}`;
    if (data[key]) return normalizeOpenLibrary(isbn, data[key]);
  } catch { /* fallthrough */ }

  // Fallback: Google Books
  try {
    const res = await fetch(`https://www.googleapis.com/books/v1/volumes?q=isbn:${isbn}`);
    const data = await res.json();
    if (data.totalItems > 0) return normalizeGoogleBooks(isbn, data.items[0]);
  } catch { /* fallthrough */ }

  return null;
}

function normalizeOpenLibrary(isbn, d) {
  const authors = (d.authors ?? []).map(a => a.name).join(', ');
  const subjects = (d.subjects ?? []).map(s => s.name ?? s).slice(0, 10);
  return {
    // Grid fields
    isbn,
    title:  d.title ?? '',
    author: authors,
    year:   d.publish_date ? parseInt(d.publish_date.slice(-4)) : null,
    cover:  `covers/${isbn}.webp`,
    // Detail fields
    publisher:   (d.publishers ?? []).map(p => p.name).join(', '),
    pages:       d.number_of_pages ?? null,
    language:    (d.languages ?? []).map(l => l.key?.replace('/languages/', '')).join(', '),
    description: d.notes ?? d.excerpts?.[0]?.text ?? '',
    subjects,
    coverUrl:    d.cover?.large ?? d.cover?.medium ?? null,
    source:      'openlibrary',
  };
}

function normalizeGoogleBooks(isbn, item) {
  const v = item.volumeInfo ?? {};
  return {
    isbn,
    title:  v.title ?? '',
    author: (v.authors ?? []).join(', '),
    year:   v.publishedDate ? parseInt(v.publishedDate.slice(0, 4)) : null,
    cover:  `covers/${isbn}.webp`,
    publisher:   v.publisher ?? '',
    pages:       v.pageCount ?? null,
    language:    v.language ?? '',
    description: v.description ?? '',
    subjects:    (v.categories ?? []).slice(0, 10),
    coverUrl:    v.imageLinks?.extraLarge
                 ?? v.imageLinks?.large
                 ?? v.imageLinks?.thumbnail
                 ?? null,
    source: 'google',
  };
}

export async function fetchCoverAsBase64(url) {
  // Proxy via allorigins to avoid CORS on cover images
  const proxy = `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`;
  const res = await fetch(proxy);
  if (!res.ok) throw new Error('Cover fetch failed');
  const blob = await res.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]); // strip data: prefix
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}
