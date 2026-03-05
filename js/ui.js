// js/ui.js — Shared UI utilities

// ─── Toast notifications ─────────────────────────────────────────────────────

let _toastContainer = null;

function getToastContainer() {
  if (_toastContainer) return _toastContainer;
  _toastContainer = document.createElement('div');
  _toastContainer.id = 'toast-container';
  document.body.appendChild(_toastContainer);
  return _toastContainer;
}

export function toast(message, type = 'info', duration = 3500) {
  const container = getToastContainer();
  const el = document.createElement('div');
  el.className = `toast toast--${type}`;
  el.textContent = message;
  container.appendChild(el);

  requestAnimationFrame(() => el.classList.add('toast--visible'));

  setTimeout(() => {
    el.classList.remove('toast--visible');
    el.addEventListener('transitionend', () => el.remove(), { once: true });
  }, duration);
}

// ─── Loading overlay ─────────────────────────────────────────────────────────

export function showLoader(message = 'Loading…') {
  let el = document.getElementById('global-loader');
  if (!el) {
    el = document.createElement('div');
    el.id = 'global-loader';
    el.innerHTML = `<div class="loader__spinner"></div><p class="loader__msg"></p>`;
    document.body.appendChild(el);
  }
  el.querySelector('.loader__msg').textContent = message;
  el.classList.add('loader--visible');
}

export function hideLoader() {
  const el = document.getElementById('global-loader');
  if (el) el.classList.remove('loader--visible');
}

// ─── Book card renderer ───────────────────────────────────────────────────────

export function renderBookCard(book) {
  const isRead    = book.reading !== null && book.reading !== undefined;
  const isMarked  = isRead && book.reading.marked;
  const coverSrc  = book.cover ?? 'assets/no-cover.svg';

  const card = document.createElement('article');
  card.className = `book-card${isRead ? ' book-card--read' : ''}${isMarked ? ' book-card--marked' : ''}`;
  card.dataset.isbn = book.isbn;

  card.innerHTML = `
    <div class="book-card__cover-wrap">
      <img class="book-card__cover" src="${coverSrc}" alt="${escHtml(book.title)}" loading="lazy"
           onerror="this.src='assets/no-cover.svg'">
      ${isRead    ? '<span class="book-card__badge book-card__badge--read" title="Read">✓</span>' : ''}
      ${isMarked  ? '<span class="book-card__badge book-card__badge--fav"  title="Favourite">★</span>' : ''}
    </div>
    <div class="book-card__info">
      <h3 class="book-card__title">${escHtml(book.title)}</h3>
      <p  class="book-card__author">${escHtml(book.author ?? '')}</p>
      ${book.year ? `<p class="book-card__year">${book.year}</p>` : ''}
    </div>
  `;

  card.addEventListener('click', () => openBookDetail(book.isbn));
  return card;
}

// ─── Book detail modal ────────────────────────────────────────────────────────

export function openBookDetail(isbn) {
  window.location.href = `book.html?isbn=${encodeURIComponent(isbn)}`;
}

// ─── Filter/sort bar ──────────────────────────────────────────────────────────

export function buildFilterBar(onFilter) {
  const bar = document.createElement('div');
  bar.className = 'filter-bar';
  bar.innerHTML = `
    <button class="filter-btn filter-btn--active" data-filter="all">All</button>
    <button class="filter-btn" data-filter="read">Read</button>
    <button class="filter-btn" data-filter="unread">Unread</button>
    <button class="filter-btn" data-filter="marked">Favourites</button>
    <select class="filter-sort" aria-label="Sort">
      <option value="title">Title A–Z</option>
      <option value="title-desc">Title Z–A</option>
      <option value="year-desc">Newest first</option>
      <option value="year-asc">Oldest first</option>
      <option value="author">Author A–Z</option>
    </select>
  `;

  bar.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      bar.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('filter-btn--active'));
      btn.classList.add('filter-btn--active');
      const sort = bar.querySelector('.filter-sort').value;
      onFilter(btn.dataset.filter, sort);
    });
  });

  bar.querySelector('.filter-sort').addEventListener('change', e => {
    const active = bar.querySelector('.filter-btn--active');
    onFilter(active?.dataset.filter ?? 'all', e.target.value);
  });

  return bar;
}

export function applyFilterSort(books, filter, sort) {
  let result = books.slice();

  switch (filter) {
    case 'read':    result = result.filter(b => b.reading); break;
    case 'unread':  result = result.filter(b => !b.reading); break;
    case 'marked':  result = result.filter(b => b.reading?.marked); break;
  }

  switch (sort) {
    case 'title':       result.sort((a, b) => (a.title ?? '').localeCompare(b.title ?? '')); break;
    case 'title-desc':  result.sort((a, b) => (b.title ?? '').localeCompare(a.title ?? '')); break;
    case 'year-desc':   result.sort((a, b) => (b.year ?? 0) - (a.year ?? 0)); break;
    case 'year-asc':    result.sort((a, b) => (a.year ?? 0) - (b.year ?? 0)); break;
    case 'author':      result.sort((a, b) => (a.author ?? '').localeCompare(b.author ?? '')); break;
  }

  return result;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

export function escHtml(str) {
  return (str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

export function formatDate(ddmmyyyy) {
  if (!ddmmyyyy) return '';
  const [d, m, y] = ddmmyyyy.split('/');
  const months = ['gennaio','febbraio','marzo','aprile','maggio','giugno',
                  'luglio','agosto','settembre','ottobre','novembre','dicembre'];
  return `${parseInt(d)} ${months[parseInt(m) - 1]} ${y}`;
}
