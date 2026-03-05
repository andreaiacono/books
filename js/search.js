// js/search.js — Lunr-based full-text search over the enriched catalog

let _index = null;
let _bookMap = null;   // isbn -> enriched book (for result hydration)

// ─── Index builder ───────────────────────────────────────────────────────────

export async function buildSearchIndex(enrichedBooks) {
  _bookMap = new Map(enrichedBooks.map(b => [b.isbn, b]));

  _index = lunr(function () {
    this.ref('isbn');

    // Field weights: title matters most, then author, then subjects/description
    this.field('title',       { boost: 10 });
    this.field('author',      { boost: 5  });
    this.field('subjects',    { boost: 3  });
    this.field('year',        { boost: 1  });
    this.field('publisher',   { boost: 1  });
    this.field('description', { boost: 1  });

    enrichedBooks.forEach(book => {
      this.add({
        isbn:        book.isbn,
        title:       book.title ?? '',
        author:      book.author ?? '',
        subjects:    Array.isArray(book.subjects) ? book.subjects.join(' ') : '',
        year:        book.year ? String(book.year) : '',
        publisher:   book.publisher ?? '',
        description: book.description ?? '',
      });
    });
  });

  return _index;
}

// ─── Search ──────────────────────────────────────────────────────────────────

export function search(query) {
  if (!_index || !query?.trim()) return [];

  const q = query.trim();

  // If query uses explicit Lunr syntax, pass through directly
  if (/[:"~^+\-]/.test(q) || q.includes('*')) {
    try {
      return hydrateResults(_index.search(q));
    } catch {
      return [];
    }
  }

  // Plain query: apply fuzzy (edit distance 2) + trailing wildcard per term
  try {
    const terms = q.split(/\s+/);
    return hydrateResults(_index.query(function () {
      terms.forEach(term => {
        this.term(term, { editDistance: 1 });
        this.term(term, { wildcard: lunr.Query.wildcard.TRAILING });
      });
    }));
  } catch {
    return [];
  }
}

// Field-scoped search: search(query, 'title') or search(query, 'author')
export function searchField(query, field) {
  if (!_index || !query?.trim()) return [];
  try {
    return hydrateResults(_index.search(`${field}:${query.trim()}`));
  } catch {
    return [];
  }
}

function hydrateResults(results) {
  return results
      .map(r => _bookMap.get(r.ref))
      .filter(Boolean);
}

export function isIndexReady() {
  return _index !== null;
}

