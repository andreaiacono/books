// js/data.js — Data layer: loads, caches, and joins all data sources

const DATA = {
  grid: null,        // [{isbn, title, author, year, cover, description, subjects, …}]
  readMap: null,     // Map<isbn, readingLogEntry>
};

// ─── Loaders ────────────────────────────────────────────────────────────────

export async function loadGrid() {
  if (DATA.grid) return DATA.grid;
  const res = await fetch('data/books.json');
  if (!res.ok) throw new Error('Could not load books.json');
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
    branch: localStorage.getItem('gh_branch') || null,
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
    body: JSON.stringify({ message, content, sha, ...(branch ? { branch } : {}) }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(`GitHub PUT failed: ${res.status} — ${err.message ?? path}`);
  }
  return res.json();
}

// ─── Book persistence ───────────────────────────────────────────────────────

async function ghGetGridJson() {
  // If we recently saved and have a cached SHA + grid data, use those.
  // The API content may be stale for several seconds after a commit, so using
  // it would silently discard changes from the previous save.
  const cachedSha = sessionStorage.getItem('books_json_sha');
  const cachedGrid = sessionStorage.getItem('books_json_grid');
  if (cachedSha && cachedGrid) {
    return { sha: cachedSha, grid: JSON.parse(cachedGrid) };
  }

  // books.json may exceed 1 MB — GitHub Contents API returns empty content for
  // large files.  Fetch metadata (for SHA), then content via download_url.
  const { token, repo } = getConfig();
  const meta = await fetch(`${GITHUB_API}/repos/${repo}/contents/data/books.json`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
  });
  if (!meta.ok) throw new Error(`GitHub GET failed: ${meta.status} data/books.json`);
  const info = await meta.json();

  let text;
  if (info.content) {
    text = decodeURIComponent(escape(atob(info.content.replace(/\n/g, ''))));
  } else {
    const raw = await fetch(info.download_url);
    if (!raw.ok) throw new Error(`Download failed: ${raw.status}`);
    text = await raw.text();
  }
  return { sha: info.sha, grid: JSON.parse(text) };
}

export async function saveNewBook(entry, coverBase64, coverMime) {
  // entry:       full merged book object (grid + detail fields)
  // coverBase64: raw base64 string (or null to skip)
  // coverMime:   e.g. 'image/webp'

  const steps = [];

  // 1. Upload cover if provided
  if (coverBase64) {
    const coverPath = `covers/${entry.isbn}.webp`;
    let coverSha;
    try { const f = await ghGet(coverPath); coverSha = f.sha; } catch { /* new file */ }
    await ghPut(coverPath, coverBase64, coverSha, `cover: ${entry.isbn}`);
    steps.push('cover');
  }

  // 2. Update books.json (retry once on 409 SHA conflict)
  async function putGrid() {
    const { sha, grid: currentGrid } = await ghGetGridJson();
    const idx = currentGrid.findIndex(b => b.isbn === entry.isbn);
    const isUpdate = idx >= 0;
    if (isUpdate) currentGrid[idx] = entry;
    else currentGrid.push(entry);
    const jsonStr = '[\n' + currentGrid.map(b => JSON.stringify(b)).join(',\n') + '\n]\n';
    const gridContent = btoa(unescape(encodeURIComponent(jsonStr)));
    return { gridContent, sha, isUpdate, updatedGrid: currentGrid };
  }

  let result = await putGrid();
  let putRes;
  try {
    putRes = await ghPut('data/books.json', result.gridContent, result.sha, `${result.isUpdate ? 'edit' : 'add'}: ${entry.title}`);
  } catch (e) {
    if (!e.message?.includes('409')) throw e;
    // SHA conflict — clear cache, re-fetch, and retry once
    sessionStorage.removeItem('books_json_sha');
    sessionStorage.removeItem('books_json_grid');
    result = await putGrid();
    putRes = await ghPut('data/books.json', result.gridContent, result.sha, `${result.isUpdate ? 'edit' : 'add'}: ${entry.title}`);
  }
  // Cache SHA + full grid in sessionStorage so subsequent saves (even after
  // page navigation) use the latest data instead of stale API content.
  sessionStorage.setItem('books_json_sha', putRes.content?.sha ?? '');
  sessionStorage.setItem('books_json_grid', JSON.stringify(result.updatedGrid));
  steps.push('grid');

  // Update local cache
  if (DATA.grid) {
    const i = DATA.grid.findIndex(b => b.isbn === entry.isbn);
    if (i >= 0) DATA.grid[i] = entry; else DATA.grid.push(entry);
  }

  return steps;
}

// ─── Reading log persistence ─────────────────────────────────────────────────

export async function appendReadingLogEntry({ date, title, comment, creators, isbn, marked }) {
  function csvField(v) {
    const s = String(v ?? '');
    return `"${s.replace(/"/g, '""')}"`;
  }
  const row = [date, title, comment, creators, isbn, String(marked)].map(csvField).join(',');

  const csvFile = await ghGet('data/reading-log.csv');
  const current = decodeURIComponent(escape(atob(csvFile.content.replace(/\n/g, ''))));
  const updated = current.trimEnd() + '\n' + row;
  const content = btoa(unescape(encodeURIComponent(updated)));
  await ghPut('data/reading-log.csv', content, csvFile.sha, `log: ${title}`);
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
    added:  new Date().toISOString().slice(0, 10),
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
    added:  new Date().toISOString().slice(0, 10),
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
