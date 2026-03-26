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

export async function saveBulkSubjects(changes /* Map<isbn, string[]> */) {
  const { sha, grid: currentGrid } = await ghGetGridJson();
  for (const [isbn, subjects] of changes) {
    const book = currentGrid.find(b => b.isbn === isbn);
    if (book) book.subjects = subjects;
  }
  const jsonStr = '[\n' + currentGrid.map(b => JSON.stringify(b)).join(',\n') + '\n]\n';
  const gridContent = btoa(unescape(encodeURIComponent(jsonStr)));

  let putRes;
  try {
    putRes = await ghPut('data/books.json', gridContent, sha, `bulk: update ${changes.size} subject(s)`);
  } catch (e) {
    if (!e.message?.includes('409')) throw e;
    sessionStorage.removeItem('books_json_sha');
    sessionStorage.removeItem('books_json_grid');
    const fresh = await ghGetGridJson();
    for (const [isbn, subjects] of changes) {
      const book = fresh.grid.find(b => b.isbn === isbn);
      if (book) book.subjects = subjects;
    }
    const js2 = '[\n' + fresh.grid.map(b => JSON.stringify(b)).join(',\n') + '\n]\n';
    putRes = await ghPut('data/books.json', btoa(unescape(encodeURIComponent(js2))), fresh.sha, `bulk: update ${changes.size} subject(s)`);
  }
  sessionStorage.setItem('books_json_sha', putRes.content?.sha ?? '');
  sessionStorage.setItem('books_json_grid', JSON.stringify(currentGrid));
  if (DATA.grid) {
    for (const [isbn, subjects] of changes) {
      const book = DATA.grid.find(b => b.isbn === isbn);
      if (book) book.subjects = subjects;
    }
  }
}

export async function saveBulkAuthors(changes /* Map<isbn, string> */) {
  const { sha, grid: currentGrid } = await ghGetGridJson();
  let actualChanges = 0;
  for (const [isbn, author] of changes) {
    const book = currentGrid.find(b => b.isbn === isbn);
    if (book && book.author !== author) { book.author = author; actualChanges++; }
  }
  if (actualChanges === 0) throw new Error('No actual changes to save (authors already match)');

  const jsonStr = '[\n' + currentGrid.map(b => JSON.stringify(b)).join(',\n') + '\n]\n';
  const gridContent = btoa(unescape(encodeURIComponent(jsonStr)));

  let putRes;
  try {
    putRes = await ghPut('data/books.json', gridContent, sha, `bulk: update ${actualChanges} author(s)`);
  } catch (e) {
    if (!e.message?.includes('409')) throw e;
    sessionStorage.removeItem('books_json_sha');
    sessionStorage.removeItem('books_json_grid');
    const fresh = await ghGetGridJson();
    actualChanges = 0;
    for (const [isbn, author] of changes) {
      const book = fresh.grid.find(b => b.isbn === isbn);
      if (book && book.author !== author) { book.author = author; actualChanges++; }
    }
    if (actualChanges === 0) throw new Error('No actual changes to save (authors already match)');
    const js2 = '[\n' + fresh.grid.map(b => JSON.stringify(b)).join(',\n') + '\n]\n';
    putRes = await ghPut('data/books.json', btoa(unescape(encodeURIComponent(js2))), fresh.sha, `bulk: update ${actualChanges} author(s)`);
  }
  sessionStorage.setItem('books_json_sha', putRes.content?.sha ?? '');
  sessionStorage.setItem('books_json_grid', JSON.stringify(currentGrid));
  if (DATA.grid) {
    for (const [isbn, author] of changes) {
      const book = DATA.grid.find(b => b.isbn === isbn);
      if (book) book.author = author;
    }
  }
}

export async function saveBulkCovers(covers /* Map<isbn, base64string> */, onProgress) {
  const { token, repo, branch: cfgBranch } = getConfig();
  const branch = cfgBranch || 'master';
  const headers = { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' };
  const api = `${GITHUB_API}/repos/${repo}/git`;

  // 1. Get HEAD commit & its tree SHA
  const refRes = await fetch(`${api}/refs/heads/${branch}`, { headers });
  if (!refRes.ok) throw new Error(`Failed to get ref: ${refRes.status}`);
  const refData = await refRes.json();
  const baseCommitSha = refData.object.sha;

  const commitRes = await fetch(`${api}/commits/${baseCommitSha}`, { headers });
  if (!commitRes.ok) throw new Error(`Failed to get commit: ${commitRes.status}`);
  const baseTreeSha = (await commitRes.json()).tree.sha;

  // 2. Create blobs for each cover
  const treeItems = [];
  let done = 0;
  for (const [isbn, base64] of covers) {
    const blobRes = await fetch(`${api}/blobs`, {
      method: 'POST', headers,
      body: JSON.stringify({ content: base64, encoding: 'base64' }),
    });
    if (!blobRes.ok) throw new Error(`Failed to create blob for ${isbn}: ${blobRes.status}`);
    const blob = await blobRes.json();
    treeItems.push({ path: `covers/${isbn}.webp`, mode: '100644', type: 'blob', sha: blob.sha });
    done++;
    if (onProgress) onProgress(done, covers.size, 'blobs');
  }

  // 3. Create tree
  const treeRes = await fetch(`${api}/trees`, {
    method: 'POST', headers,
    body: JSON.stringify({ base_tree: baseTreeSha, tree: treeItems }),
  });
  if (!treeRes.ok) throw new Error(`Failed to create tree: ${treeRes.status}`);
  const newTreeSha = (await treeRes.json()).sha;

  // 4. Create commit
  const commitCreateRes = await fetch(`${api}/commits`, {
    method: 'POST', headers,
    body: JSON.stringify({
      message: `bulk: update ${covers.size} cover(s)`,
      tree: newTreeSha,
      parents: [baseCommitSha],
    }),
  });
  if (!commitCreateRes.ok) throw new Error(`Failed to create commit: ${commitCreateRes.status}`);
  const newCommitSha = (await commitCreateRes.json()).sha;

  // 5. Update ref
  const updateRes = await fetch(`${GITHUB_API}/repos/${repo}/git/refs/heads/${branch}`, {
    method: 'PATCH', headers,
    body: JSON.stringify({ sha: newCommitSha }),
  });
  if (!updateRes.ok) throw new Error(`Failed to update ref: ${updateRes.status}`);
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
// Priority: IBS.it → Google Books web → Open Library → Google Books API
// (mirrors tools/fetch_data.py)

const CORS_PROXY = 'https://api.allorigins.win/raw?url=';

async function fetchIBS(isbn) {
  // Scrape IBS.it JSON-LD structured data (via CORS proxy)
  try {
    const url = `${CORS_PROXY}${encodeURIComponent(`https://www.ibs.it/a/e/${isbn}`)}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) return {};
    const page = await res.text();

    const m = page.match(/<script\s+type="application\/ld\+json">([\s\S]*?)<\/script>/);
    if (!m) return {};

    let ld = JSON.parse(m[1]);
    if (Array.isArray(ld)) ld = ld.find(x => (x['@type'] || []).includes('Book')) || ld[0] || {};
    if (ld.mainEntity) ld = ld.mainEntity;

    const meta = {};
    const desc = (ld.description || '').trim();
    if (desc.length > 40) meta.description = desc;
    if (ld.publisher) meta.publisher = String(ld.publisher).trim();
    const pages = parseInt(ld.numberOfPages);
    if (pages > 0) meta.pages = pages;
    if (ld.author) meta.author = String(ld.author).trim();
    if (ld.name) meta.title = String(ld.name).trim();
    const dateM = (ld.datePublished || '').match(/(\d{4})/);
    if (dateM) meta.year = parseInt(dateM[1]);
    return meta;
  } catch { return {}; }
}

async function fetchGoogleBooksWeb(isbn) {
  // Scrape Google Books website (via CORS proxy)
  try {
    const url = `${CORS_PROXY}${encodeURIComponent(`https://books.google.com/books?vid=${isbn}`)}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) return {};
    const page = await res.text();

    const meta = {};

    // Description from <meta name="description">
    const descM = page.match(/<meta\s+name="description"\s+content="([^"]+)"/);
    if (descM) {
      const desc = descM[1].replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").trim();
      if (desc.length > 40) meta.description = desc;
    }

    // Bibliographic info table rows
    const rows = [...page.matchAll(/<td class="metadata_label">.*?<span[^>]*>([^<]+)<\/span>[\s\S]*?<td class="metadata_value">.*?<span[^>]*>([\s\S]*?)<\/span>/g)];
    for (const [, rawLabel, rawValue] of rows) {
      const label = rawLabel.replace(/&\w+;/g, '').trim().toLowerCase();
      const value = rawValue.replace(/<[^>]+>/g, '').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").trim();
      if (!value) continue;
      if (['editore','publisher','éditeur','verlag','editorial'].includes(label))
        meta.publisher = value.replace(/,\s*\d{4}$/, '').trim();
      if (['lunghezza','length','longueur','länge','longitud','pages','pagine'].includes(label)) {
        const pm = value.match(/(\d+)/);
        if (pm) meta.pages = parseInt(pm[1]);
      }
      if (['autore','author','auteur','autor'].includes(label) && !meta.author)
        meta.author = value;
      if (['data di pubblicazione','published','date de publication','veröffentlichungsdatum','año de edición'].includes(label)) {
        const ym = value.match(/(\d{4})/);
        if (ym) meta.year = parseInt(ym[1]);
      }
    }
    return meta;
  } catch { return {}; }
}

async function fetchOpenLibrary(isbn) {
  try {
    const res = await fetch(`https://openlibrary.org/api/books?bibkeys=ISBN:${isbn}&jscmd=data&format=json`);
    const data = await res.json();
    const d = data[`ISBN:${isbn}`];
    if (!d) return {};

    const meta = {};
    if (d.title) meta.title = d.title;
    const authors = (d.authors ?? []).map(a => a.name).join(', ');
    if (authors) meta.author = authors;
    if (d.publish_date) { const y = parseInt(d.publish_date.slice(-4)); if (y) meta.year = y; }
    const pub = (d.publishers ?? []).map(p => p.name).join(', ');
    if (pub) meta.publisher = pub;
    if (d.number_of_pages) meta.pages = d.number_of_pages;
    const lang = (d.languages ?? []).map(l => l.key?.replace('/languages/', '')).join(', ');
    if (lang) meta.lang = lang;
    const desc = d.notes ?? d.excerpts?.[0]?.text ?? '';
    if (desc) meta.description = typeof desc === 'object' ? desc.value : desc;
    const subjects = (d.subjects ?? []).map(s => s.name ?? s).slice(0, 10);
    if (subjects.length) meta.subjects = subjects;
    meta.coverUrl = d.cover?.large ?? d.cover?.medium ?? null;
    return meta;
  } catch { return {}; }
}

async function fetchGoogleBooksAPI(isbn) {
  try {
    const res = await fetch(`https://www.googleapis.com/books/v1/volumes?q=isbn:${isbn}`);
    const data = await res.json();
    if (!data.totalItems || !data.items?.length) return {};

    const item = data.items[0];
    let v = item.volumeInfo ?? {};

    // Fetch detailed volume info if missing key fields
    if ((!v.description || !v.publisher || !v.pageCount) && item.selfLink) {
      try {
        const r2 = await fetch(item.selfLink);
        if (r2.ok) {
          const vol = (await r2.json()).volumeInfo ?? {};
          for (const k of ['description', 'publisher', 'pageCount']) {
            if (!v[k] && vol[k]) v[k] = vol[k];
          }
        }
      } catch { /* ignore */ }
    }

    const meta = {};
    if (v.title) meta.title = v.title;
    if (v.authors?.length) meta.author = v.authors.join(', ');
    if (v.publishedDate) { const y = parseInt(v.publishedDate.slice(0, 4)); if (y) meta.year = y; }
    if (v.publisher) meta.publisher = v.publisher;
    if (v.pageCount > 0) meta.pages = v.pageCount;
    if (v.language) meta.lang = v.language;
    if (v.description) meta.description = v.description;
    if (v.categories?.length) meta.subjects = v.categories.slice(0, 10);
    meta.coverUrl = v.imageLinks?.extraLarge ?? v.imageLinks?.large ?? v.imageLinks?.thumbnail ?? null;
    return meta;
  } catch { return {}; }
}

export async function fetchISBNMetadata(isbn) {
  // Fetch from all sources in parallel
  const [ibs, gbWeb, ol, gbApi] = await Promise.all([
    fetchIBS(isbn),
    fetchGoogleBooksWeb(isbn),
    fetchOpenLibrary(isbn),
    fetchGoogleBooksAPI(isbn),
  ]);

  // Merge in priority order: IBS > Google Books web > Open Library > Google Books API
  const sources = [ibs, gbWeb, ol, gbApi];
  const fields = ['title', 'author', 'year', 'publisher', 'pages', 'lang', 'description', 'subjects', 'coverUrl'];
  const merged = {};
  for (const field of fields) {
    for (const src of sources) {
      const val = src[field];
      if (val !== undefined && val !== null && val !== '') {
        if (Array.isArray(val) ? val.length > 0 : true) {
          merged[field] = val;
          break;
        }
      }
    }
  }

  if (!merged.title && !merged.author) return null;

  return {
    isbn,
    title:       merged.title ?? '',
    author:      merged.author ?? '',
    year:        merged.year ?? null,
    cover:       `covers/${isbn}.webp`,
    added:       new Date().toISOString().slice(0, 10),
    publisher:   merged.publisher ?? '',
    pages:       merged.pages ?? null,
    lang:        merged.lang ?? '',
    description: merged.description ?? '',
    subjects:    merged.subjects ?? [],
    coverUrl:    merged.coverUrl ?? null,
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
