// js/search.js — Lunr-based full-text search over the enriched catalog

let _index = null;
let _bookMap = null;      // isbn -> enriched book (for result hydration)
let _indexPipeline = null; // the *indexing* pipeline — see addTerm()

// ─── Diacritics removal ─────────────────────────────────────────────────────

const EXTRA_MAP = { ø: 'o', Ø: 'O', ł: 'l', Ł: 'L', đ: 'd', Đ: 'D', æ: 'ae', Æ: 'AE', ß: 'ss' };
function stripDiacritics(s) {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[øØłŁđĐæÆß]/g, c => EXTRA_MAP[c]);
}

const removeDiacritics = function (token) {
  return token.update(stripDiacritics);
};
lunr.Pipeline.registerFunction(removeDiacritics, 'removeDiacritics');

// Split on apostrophes so "L'altra" tokenises as ["l", "altra"]
lunr.tokenizer.separator = /[\s\-''\u2019]+/;

// ─── Index builder ───────────────────────────────────────────────────────────

export function buildSearchIndex(books) {
  _bookMap = new Map(books.map(b => [b.isbn, b]));

  _index = lunr(function () {
    this.use(lunr.multiLanguage('en', 'it'));
    this.ref('isbn');

    // Strip diacritics in both index and search pipelines
    this.pipeline.add(removeDiacritics);
    this.searchPipeline.add(removeDiacritics);

    // Keep a handle on the indexing pipeline: unlike the search pipeline it
    // includes the stop word filter, so it is the only way to tell what tokens
    // actually made it into the index.
    _indexPipeline = this.pipeline;

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

  // Explicit Lunr syntax (fields, boosts, fuzziness, wildcards, +/-): let Lunr
  // parse it, then promote every clause the user did not mark to REQUIRED so
  // these queries AND like plain ones do. Lunr's own default is OPTIONAL (OR);
  // an explicit "-" stays PROHIBITED.
  if (/[:"~^+\-]/.test(q) || q.includes('*')) {
    return runQuery(b => {
      const parsed = new lunr.Query(_index.fields);
      // Lowercased and de-quoted first: see expandPhrases() and the note on
      // lowercasing in stemOf().
      new lunr.QueryParser(expandPhrases(q.toLowerCase()), parsed).parse();
      // Punctuation-only input parses to nothing, and a clauseless Lunr query
      // matches every document — throw so runQuery() reports no results.
      if (!parsed.clauses.length) throw new Error('no clauses');
      for (const clause of parsed.clauses) {
        if (clause.presence === lunr.Query.presence.OPTIONAL) {
          clause.presence = lunr.Query.presence.REQUIRED;
        }
        b.clause(clause);
      }
    }, q);
  }

  // Plain query: every term must match (AND), stemmed.
  const terms = q.split(/[\s''’]+/).filter(Boolean);
  if (!terms.length) return [];

  // Stem through the *indexing* pipeline, not the search one: only the former
  // applies the stop word filter, so it alone says which tokens actually made
  // it into the index. A stop word like "il" stems to nothing and is dropped,
  // rather than requiring a term no document can hold.
  const stems = terms.map(stemOf).filter(Boolean);

  if (stems.length) {
    // Pass 1 — all terms required, exact stemmed match.
    const exact = runQuery(b => {
      for (const s of stems) addTerm(b, s, false);
    }, q);
    if (exact.length) return exact;

    // Pass 2 — same, but the last term is treated as a prefix, since it may
    // still be half-typed. The wildcard goes on the *stem*: appending it to the
    // raw term first blocks the stemmer ("barone*" stays whole while the index
    // holds "baron"), which is why AND queries used to come back empty and fall
    // through to an OR.
    const prefixLast = runQuery(b => {
      stems.forEach((s, i) => addTerm(b, s, i === stems.length - 1));
    }, q);
    if (prefixLast.length) return prefixLast;

    // Pass 3 — every term as a prefix, for partial input throughout.
    return runQuery(b => {
      for (const s of stems) addTerm(b, s, true);
    }, q);
  }

  // Nothing survived the stop word filter — someone typed only "il", or is one
  // keystroke into a word. Retry on the raw terms so typing still gives
  // feedback instead of an empty list.
  return runQuery(b => {
    for (const term of terms) {
      addTerm(b, stripDiacritics(term.toLowerCase()), true);
    }
  }, q);
}

// Stem a raw term the way the indexer did. Lowercasing matters and is easy to
// miss: lunr lowercases in its *tokenizer*, which the indexer runs but a direct
// runString() call does not — so "Calvino" would stem to "Calvino" and never
// match the indexed "calvin".
function stemOf(term) {
  return _indexPipeline.runString(term.toLowerCase(), {})[0];
}

// Lunr has no phrase support: it would lex "jack london" into the terms
// `"jack` and `london"`, quotes included, which match nothing. Rewrite a quoted
// group as one required clause per word, keeping any field prefix — so
// author:"jack london" becomes +author:jack +author:london. That is "all these
// words in this field" rather than strict adjacency, which lunr cannot express
// without positional metadata, but it is what the quotes are used for here.
function expandPhrases(q) {
  return q.replace(/(?:(\w+):)?"([^"]*)"/g, (whole, field, phrase) => {
    const words = phrase.split(/\s+/).filter(Boolean);
    if (!words.length) return '';
    return words.map(w => (field ? `${field}:${w}` : w)).join(' ');
  });
}

// Add one REQUIRED clause for an already-stemmed token.
function addTerm(builder, stem, prefix) {
  const opts = { usePipeline: false, presence: lunr.Query.presence.REQUIRED };
  if (prefix) opts.wildcard = lunr.Query.wildcard.TRAILING;
  builder.term(stem, opts);
}

function runQuery(build, q) {
  try {
    return hydrateResults(_index.query(build), q);
  } catch {
    return [];
  }
}

function hydrateResults(results, query) {
  const books = results.map(r => _bookMap.get(r.ref)).filter(Boolean);
  if (!query) return books;

  // Re-rank: promote books whose title contains the query terms
  const q = stripDiacritics(query.trim().toLowerCase());
  const qTerms = q.split(/\s+/);

  const scored = books.map(b => ({ book: b, score: titleScore(b, q, qTerms) }));
  scored.sort((a, b) => b.score - a.score);
  return scored.map(s => s.book);
}

function titleScore(book, query, queryTerms) {
  const t = stripDiacritics((book.title ?? '').toLowerCase());
  // Exact substring match (e.g. "materia oscura" in "La materia oscura")
  if (t.includes(query)) return 3;
  // All query terms present in title
  if (queryTerms.every(w => t.includes(w))) return 2;
  // At least one term in title
  if (queryTerms.some(w => t.includes(w))) return 1;
  return 0;
}

export function isIndexReady() {
  return _index !== null;
}
