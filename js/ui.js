import { MONTHS } from './constants.js';

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
  const isRemoved = book.removed === true;
  const coverSrc  = book.cover ?? 'assets/no-cover.svg';
  const comment   = isRead && book.reading.comment?.trim() ? book.reading.comment.trim() : '';

  const card = document.createElement('article');
  card.className = `book-card${isRead ? ' book-card--read' : ''}${isMarked ? ' book-card--marked' : ''}${isRemoved ? ' book-card--removed' : ''}`;
  card.dataset.isbn = book.isbn;

  const bookUrl = `book.html?isbn=${encodeURIComponent(book.isbn)}`;
  // An exact-author param rather than a search query: index.html can apply it
  // to the catalog directly, so the page paints just this author's books
  // instead of rendering the whole library and waiting on the Lunr index.
  const authorSearchUrl = book.author ? `index.html?author=${encodeURIComponent(book.author)}` : '#';

  card.innerHTML = `
    <a class="book-card__link" href="${bookUrl}"${comment ? ` title="${escHtml(comment)}"` : ''}>
      <div class="book-card__cover-wrap">
        <img class="book-card__cover" src="${coverSrc}" alt="${escHtml(book.title)}" loading="lazy"
             onerror="this.src='assets/no-cover.svg'">
        ${isRemoved ? '<span class="book-card__badge book-card__badge--removed" title="Removed">Removed</span>' : ''}
      </div>
      <div class="book-card__info">
        <h3 class="book-card__title">${isMarked ? '<span class="book-card__star" title="Favourite">★</span>' : ''}${escHtml(book.title)}</h3>
        <p class="book-card__author">
          ${book.author
            ? `<a href="${authorSearchUrl}" class="author-link" onclick="event.stopPropagation()">${escHtml(book.author)}</a>`
            : ''}
        </p>
        ${book.year ? `<p class="book-card__year">${book.year}</p>` : ''}
      </div>
    </a>
  `;

  const img = card.querySelector('.book-card__cover');
  const wrap = card.querySelector('.book-card__cover-wrap');
  img.addEventListener('load', () => {
    if (!img.naturalWidth || !img.naturalHeight) return;
    const scale = Math.min(wrap.clientWidth / img.naturalWidth, wrap.clientHeight / img.naturalHeight);
    const sideSpace = (wrap.clientWidth - img.naturalWidth * scale) / 2;
    if (sideSpace > 0) wrap.style.paddingTop = `${sideSpace}px`;
  });

  return card;
}

// ─── Book detail modal ────────────────────────────────────────────────────────

export function openBookDetail(isbn) {
  window.location.href = `book.html?isbn=${encodeURIComponent(isbn)}`;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

export function escHtml(str) {
  return (str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// The app stores two date shapes — books.json `added` is YYYY-MM-DD, the reading
// log's `date` is DD/MM/YYYY — and both reach the UI. Accepting either keeps one
// display format everywhere and removes the chance of handing a date to the
// wrong parser: the separator tells them apart unambiguously.
export function formatDate(value) {
  const str = String(value ?? '').trim();
  if (!str) return '';

  let y, m, d;
  if (str.includes('-')) [y, m, d] = str.split('-');
  else if (str.includes('/')) [d, m, y] = str.split('/');
  else return str;

  const month = MONTHS[parseInt(m, 10) - 1];
  // Unparseable input is returned as-is rather than rendered "NaN undefined".
  if (!month || !parseInt(d, 10) || !y) return str;
  return `${parseInt(d, 10)} ${month} ${y}`;
}
