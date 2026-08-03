import { LANG_LABELS } from './constants.js';
import { escHtml } from './ui.js';

// Sentinel option: picking it reveals the free-text box for a code we don't list.
const NEW = '__new__';

/**
 * The codes offered in the dropdown: the canonical ones, plus anything already
 * used in the library so an old book can never silently lose its language.
 */
function codesFor(extra = []) {
  const canonical = Object.keys(LANG_LABELS);
  const rest = [...new Set(extra.map(c => (c ?? '').trim().toLowerCase()).filter(Boolean))]
    .filter(c => !canonical.includes(c))
    .sort();
  return [...canonical, ...rest];
}

const labelFor = code => `${code} — ${LANG_LABELS[code] ?? code.toUpperCase()}`;

/**
 * Markup for the language <select> and its companion "new code" input.
 * A `selected` value that isn't in the list renders as the new-code case with
 * the box already visible and filled — that's how books imported from the APIs
 * (de, pt, la…) keep their value.
 */
export function languageSelectHtml({ selectId = 'f-language', inputId = 'f-language-new', selected = '', extra = [] } = {}) {
  const codes = codesFor(extra);
  const cur = (selected ?? '').trim();
  const custom = cur !== '' && !codes.includes(cur);

  const options = [
    `<option value=""${cur === '' ? ' selected' : ''}>— None —</option>`,
    ...codes.map(c => `<option value="${c}"${c === cur ? ' selected' : ''}>${escHtml(labelFor(c))}</option>`),
    `<option value="${NEW}"${custom ? ' selected' : ''}>+ Add another language…</option>`,
  ].join('');

  return `<select id="${selectId}">${options}</select>
    <input type="text" id="${inputId}" placeholder="Two-letter code, e.g. de"
           maxlength="8" autocomplete="off"
           value="${custom ? escHtml(cur) : ''}"
           style="margin-top:0.4rem;${custom ? '' : 'display:none'}">`;
}

/**
 * Adds codes to an already-rendered select, keeping "+ Add another…" last.
 * Used by add.html, which renders the field before the catalog has loaded.
 */
export function addLanguageOptions(selectId, codes) {
  const select = document.getElementById(selectId);
  const newOpt = [...select.options].find(o => o.value === NEW);
  for (const code of codesFor(codes)) {
    if ([...select.options].some(o => o.value === code)) continue;
    const opt = document.createElement('option');
    opt.value = code;
    opt.textContent = labelFor(code);
    select.insertBefore(opt, newOpt);
  }
}

/**
 * Wires the select to its input. Returns a get/set pair so callers never have to
 * know which of the two elements currently holds the value.
 * `onChange` fires with the effective code on every user edit.
 */
export function bindLanguageSelect(selectId, inputId, onChange) {
  const select = document.getElementById(selectId);
  const input = document.getElementById(inputId);

  const get = () => (select.value === NEW ? input.value : select.value).trim().toLowerCase();
  const showInput = on => { input.style.display = on ? '' : 'none'; };

  select.addEventListener('change', () => {
    const isNew = select.value === NEW;
    showInput(isNew);
    if (isNew) input.focus(); else input.value = '';
    onChange?.(get());
  });
  input.addEventListener('input', () => onChange?.(get()));

  return {
    get,
    set(code) {
      const c = (code ?? '').trim().toLowerCase();
      const known = [...select.options].some(o => o.value === c && o.value !== NEW);
      if (c && !known) {
        select.value = NEW; input.value = c; showInput(true);
      } else {
        select.value = c; input.value = ''; showInput(false);
      }
      onChange?.(get());
    },
  };
}
