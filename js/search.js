// js/search.js — Lunr-based full-text search over the enriched catalog

let _index = null;
let _bookMap = null;   // isbn -> enriched book (for result hydration)

// ─── Diacritics removal ─────────────────────────────────────────────────────

const EXTRA_MAP = { ø: 'o', Ø: 'O', ł: 'l', Ł: 'L', đ: 'd', Đ: 'D', æ: 'ae', Æ: 'AE', ß: 'ss' };
function stripDiacritics(s) {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[øØłŁđĐæÆß]/g, c => EXTRA_MAP[c]);
}

const removeDiacritics = function (token) {
  return token.update(stripDiacritics);
};
lunr.Pipeline.registerFunction(removeDiacritics, 'removeDiacritics');

// ─── Index builder ───────────────────────────────────────────────────────────

export function buildSearchIndex(books) {
  _bookMap = new Map(books.map(b => [b.isbn, b]));

  _index = lunr(function () {
    this.use(lunr.multiLanguage('en', 'it'));
    this.ref('isbn');

    // Strip diacritics in both index and search pipelines
    this.pipeline.add(removeDiacritics);
    this.searchPipeline.add(removeDiacritics);

    this.field('title',       { boost: 10 });
    this.field('author',      { boost: 5  });
    this.field('publisher',   { boost: 2  });
    this.field('description', { boost: 1  });

    books.forEach(book => {
      this.add({
        isbn:        book.isbn,
        title:       book.title ?? '',
        author:      book.author ?? '',
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

  // Plain query: stemmed match + trailing wildcard per term
  try {
    const terms = q.split(/\s+/);
    return hydrateResults(_index.query(function () {
      terms.forEach(term => {
        this.term(term, { usePipeline: true });  // applies stemmer
        this.term(stripDiacritics(term.toLowerCase()), { usePipeline: false, wildcard: lunr.Query.wildcard.TRAILING });
      });
    }));
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
