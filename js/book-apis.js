import { SUBJECT_KEYWORDS } from './constants.js';

// ── API key ──────────────────────────────────────────────────────────────

const GB_KEY_STORE = 'google_books_key';
const getApiKey = () => localStorage.getItem(GB_KEY_STORE) || '';

// ── Google Books ─────────────────────────────────────────────────────────

function gbUrl(params) {
  const base = 'https://www.googleapis.com/books/v1/volumes';
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') qs.set(k, String(v));
  }
  const key = getApiKey();
  if (key) qs.set('key', key);
  return `${base}?${qs}`;
}

export async function fetchGoogleBooks(query, maxResults = 10) {
  const key = getApiKey();
  if (!key) {
    console.warn('No Google Books API key set — skipping Google Books');
    return [];
  }
  const url = gbUrl({ q: query, maxResults });
  const res = await fetch(url);
  if (!res.ok) {
    console.warn(`Google Books returned ${res.status} — falling back to Open Library only`);
    return [];
  }
  const data = await res.json();
  return (data.items || []).map(normaliseGoogleItem);
}

function normaliseGoogleItem(item) {
  const v = item.volumeInfo || {};
  const isbn13 = (v.industryIdentifiers || []).find(i => i.type === 'ISBN_13')?.identifier;
  const isbn10 = (v.industryIdentifiers || []).find(i => i.type === 'ISBN_10')?.identifier;
  const isbn = isbn13 || isbn10 || '';
  const coverUrl = (v.imageLinks?.thumbnail || v.imageLinks?.smallThumbnail || '')
          .replace('http://', 'https://').replace('&edge=curl', '').replace('zoom=1', 'zoom=2');
  return {
    source:      'Google Books',
    gbId:        item.id,
    isbn,
    title:       v.title || '',
    subtitle:    v.subtitle || '',
    author:      (v.authors || []).join(', '),
    year:        parseYear(v.publishedDate),
    publisher:   v.publisher || '',
    pages:       v.pageCount || null,
    lang:        v.language || '',
    description: stripHtml(v.description || ''),
    subjects:    v.categories || [],
    coverUrl,
  };
}

// ── Open Library ─────────────────────────────────────────────────────────

export async function fetchOpenLibraryByIsbn(isbn) {
  const url = `https://openlibrary.org/api/books?bibkeys=ISBN:${isbn}&jscmd=data&format=json`;
  const res = await fetch(url);
  if (!res.ok) return null;
  const data = await res.json();
  const book = data[`ISBN:${isbn}`];
  if (!book) return null;
  return normaliseOLBook(book, isbn);
}

export async function searchOpenLibraryByTitle(title) {
  const url = `https://openlibrary.org/search.json?title=${encodeURIComponent(title)}&limit=10&fields=key,title,author_name,first_publish_year,publisher,isbn,number_of_pages_median,language,subject,cover_i,ia`;
  const res = await fetch(url);
  if (!res.ok) return [];
  const data = await res.json();
  return (data.docs || []).map(normaliseOLDoc);
}

function normaliseOLBook(book, isbn) {
  return {
    source:      'Open Library',
    isbn,
    title:       book.title || '',
    subtitle:    '',
    author:      (book.authors || []).map(a => a.name).join(', '),
    year:        book.publish_date ? parseInt(book.publish_date) || null : null,
    publisher:   (book.publishers || []).map(p => p.name).join(', '),
    pages:       book.number_of_pages || null,
    lang:        (book.languages || []).map(l => l.key.replace('/languages/','')).join(', '),
    description: typeof book.notes === 'string' ? book.notes : '',
    subjects:    (book.subjects || []).map(s => s.name || s),
    coverUrl:    book.cover?.large || book.cover?.medium || book.cover?.small || '',
  };
}

function normaliseOLDoc(doc) {
  const isbn = (doc.isbn || [])[0] || '';
  const coverId = doc.cover_i;
  const coverUrl = coverId ? `https://covers.openlibrary.org/b/id/${coverId}-M.jpg` : '';
  return {
    source:      'Open Library',
    isbn,
    title:       doc.title || '',
    subtitle:    '',
    author:      (doc.author_name || []).join(', '),
    year:        doc.first_publish_year || null,
    publisher:   (doc.publisher || [])[0] || '',
    pages:       doc.number_of_pages_median || null,
    lang:        (doc.language || [])[0] || '',
    description: '',
    subjects:    doc.subject || [],
    coverUrl,
  };
}

// ── Combined fetch by ISBN (merges Google + OL) ──────────────────────────

export async function fetchByIsbn(isbn) {
  const [gbResult, olResult] = await Promise.allSettled([
    fetchGoogleBooks(`isbn:${isbn}`, 1).then(r => r[0] || null),
    fetchOpenLibraryByIsbn(isbn),
  ]);

  const gb = gbResult.status === 'fulfilled' ? gbResult.value : null;
  const ol = olResult.status === 'fulfilled' ? olResult.value : null;

  if (!gb && !ol) return null;

  const base = gb || ol;
  const fill = gb ? ol : null;

  return {
    ...base,
    isbn:        isbn || base.isbn,
    pages:       base.pages       || fill?.pages       || null,
    publisher:   base.publisher   || fill?.publisher   || '',
    lang:        base.lang        || fill?.lang        || '',
    description: base.description || fill?.description || '',
    subjects:    mergeSubjects(base.subjects, fill?.subjects),
    coverUrl:    base.coverUrl    || fill?.coverUrl    || '',
    source:      gb && ol ? 'Google Books + Open Library'
            : gb       ? 'Google Books'
                    :             'Open Library',
  };
}

// ── Title search (Google Books + OL, deduped) ────────────────────────────

export async function searchByTitle(title) {
  const [gbRes, olRes] = await Promise.allSettled([
    fetchGoogleBooks(title, 10),
    searchOpenLibraryByTitle(title),
  ]);

  const gbBooks = gbRes.status === 'fulfilled' ? gbRes.value : [];
  const olBooks = olRes.status === 'fulfilled' ? olRes.value : [];

  const byIsbn = new Map();
  for (const b of gbBooks) {
    if (b.isbn) byIsbn.set(b.isbn, b);
    else byIsbn.set('gb_' + b.gbId, b);
  }

  for (const ol of olBooks) {
    if (ol.isbn && byIsbn.has(ol.isbn)) {
      const gb = byIsbn.get(ol.isbn);
      byIsbn.set(ol.isbn, {
        ...gb,
        pages:       gb.pages       || ol.pages,
        publisher:   gb.publisher   || ol.publisher,
        lang:        gb.lang        || ol.lang,
        description: gb.description || ol.description,
        subjects:    mergeSubjects(gb.subjects, ol.subjects),
        coverUrl:    gb.coverUrl    || ol.coverUrl,
        source:      'Google Books + Open Library',
      });
    } else {
      const key = ol.isbn || 'ol_' + Math.random();
      byIsbn.set(key, ol);
    }
  }

  return [...byIsbn.values()].slice(0, 12);
}

// ── Subject matching ─────────────────────────────────────────────────────

export function matchSubject(rawSubjects) {
  if (!rawSubjects || !rawSubjects.length) return { matched: '', candidates: [] };

  const text = rawSubjects.join(' ').toLowerCase();
  const scores = {};

  for (const [subj, keywords] of Object.entries(SUBJECT_KEYWORDS)) {
    let score = 0;
    for (const kw of keywords) {
      if (text.includes(kw)) score += kw.length;
    }
    if (score > 0) scores[subj] = score;
  }

  const sorted = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  if (!sorted.length) return { matched: '', candidates: [] };

  return {
    matched:    sorted[0][0],
    candidates: sorted.slice(0, 3).map(s => s[0]),
  };
}

// ── Utilities ────────────────────────────────────────────────────────────

function parseYear(str) {
  if (!str) return null;
  const m = str.match(/\d{4}/);
  return m ? parseInt(m[0]) : null;
}

function stripHtml(html) {
  if (!html) return '';
  return html.replace(/<[^>]+>/g, '').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').trim();
}

function mergeSubjects(a, b) {
  const all = [...(a || []), ...(b || [])];
  return [...new Set(all.map(s => String(s).toLowerCase()))].map(s =>
          all.find(x => String(x).toLowerCase() === s) || s
  );
}
