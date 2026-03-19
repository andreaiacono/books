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

  const bookUrl = `book.html?isbn=${encodeURIComponent(book.isbn)}`;
  card.innerHTML = `
    <a class="book-card__link" href="${bookUrl}">
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

export function formatDate(ddmmyyyy) {
  if (!ddmmyyyy) return '';
  const [d, m, y] = ddmmyyyy.split('/');
  const months = ['gennaio','febbraio','marzo','aprile','maggio','giugno',
                  'luglio','agosto','settembre','ottobre','novembre','dicembre'];
  return `${parseInt(d)} ${months[parseInt(m) - 1]} ${y}`;
}
