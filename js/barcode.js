// js/barcode.js — read an ISBN off a book's barcode with the device camera.
//
// Two decoders, one camera. Chrome on Android (and Chrome/Edge on most
// desktops) ship a native BarcodeDetector: hardware-backed and nothing to
// download. Firefox and Safari don't, so there we lazy-load ZXing — 360 KB, so
// only on the first scan and never as part of the app shell. The service worker
// caches it after that.
//
// Requires a secure context: getUserMedia is unavailable over plain http, so
// this works on the GitHub Pages site and on localhost, but not over a bare LAN
// IP. The caller hides the scan button when navigator.mediaDevices is missing.

const ZXING_URL = 'https://cdn.jsdelivr.net/npm/@zxing/library@0.23.0/umd/index.min.js';

// Try to decode ~10×/second rather than once per frame: a phone's camera runs
// at 30–60 fps and the extra attempts buy nothing but heat.
const DECODE_INTERVAL_MS = 100;

// ─── ISBN validation ─────────────────────────────────────────────────────────

// Book barcodes are EAN-13 in the "Bookland" range — a 978- or 979-prefixed
// ISBN-13. The other codes on a back cover (a price add-on, an ISSN, a
// warehouse label) are the same symbology, so the prefix is what tells them
// apart.
export function isBookEan(code) {
  return /^97[89]\d{10}$/.test(code) && ean13ChecksumOk(code);
}

function ean13ChecksumOk(code) {
  let sum = 0;
  for (let i = 0; i < 12; i++) sum += Number(code[i]) * (i % 2 ? 3 : 1);
  return (10 - (sum % 10)) % 10 === Number(code[12]);
}

// ─── Script loading ──────────────────────────────────────────────────────────

let zxingPromise = null;
function loadZXing() {
  if (window.ZXing) return Promise.resolve(window.ZXing);
  zxingPromise ??= new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = ZXING_URL;
    s.onload = () => (window.ZXing ? resolve(window.ZXing) : reject(new Error('ZXing did not load')));
    s.onerror = () => { zxingPromise = null; reject(new Error('ZXing did not load')); };
    document.head.appendChild(s);
  });
  return zxingPromise;
}

async function nativeDetector() {
  if (!('BarcodeDetector' in window)) return null;
  try {
    const formats = await window.BarcodeDetector.getSupportedFormats();
    if (!formats.includes('ean_13')) return null;
    return new window.BarcodeDetector({ formats: ['ean_13'] });
  } catch {
    return null;
  }
}

// ─── Overlay ─────────────────────────────────────────────────────────────────

function buildOverlay() {
  const el = document.createElement('div');
  el.className = 'scanner';
  el.innerHTML = `
    <video class="scanner__video" playsinline muted autoplay></video>
    <div class="scanner__frame"><div class="scanner__line"></div></div>
    <div class="scanner__bar">
      <p class="scanner__status">Starting camera…</p>
      <div class="scanner__buttons">
        <button type="button" class="btn btn--ghost scanner__torch" hidden>Light</button>
        <button type="button" class="btn btn--ghost scanner__cancel">Cancel</button>
      </div>
    </div>`;
  document.body.appendChild(el);
  return {
    el,
    video:  el.querySelector('.scanner__video'),
    status: el.querySelector('.scanner__status'),
    torch:  el.querySelector('.scanner__torch'),
    cancel: el.querySelector('.scanner__cancel'),
  };
}

function cameraError(err) {
  switch (err?.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'Camera access was denied — allow it for this site and try again.';
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'No camera found on this device.';
    case 'NotReadableError':
      return 'The camera is already in use by another app.';
    default:
      return 'Could not start the camera.';
  }
}

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Open the camera and scan one book barcode.
 * Resolves to { isbn } on a read, { cancelled: true } if dismissed, or
 * { error } with a message fit to show the user.
 */
export function scanIsbn() {
  if (!navigator.mediaDevices?.getUserMedia) {
    return Promise.resolve({ error: 'This browser cannot reach the camera from this page.' });
  }

  const ui = buildOverlay();
  document.body.classList.add('scanner-open');

  return new Promise(resolve => {
    let stream = null;
    let reader = null;      // ZXing, when used
    let rafId  = null;      // native detector loop
    let done   = false;

    function settle(result) {
      if (done) return;
      done = true;
      if (rafId) cancelAnimationFrame(rafId);
      try { reader?.reset(); } catch { /* already torn down */ }
      stream?.getTracks().forEach(t => t.stop());
      ui.video.srcObject = null;
      document.removeEventListener('keydown', onKey);
      document.body.classList.remove('scanner-open');
      ui.el.remove();
      resolve(result);
    }

    function onKey(e) { if (e.key === 'Escape') settle({ cancelled: true }); }
    document.addEventListener('keydown', onKey);
    ui.cancel.addEventListener('click', () => settle({ cancelled: true }));

    // A single 1D read can be a plausible misread that still passes the
    // checksum, so take the same code twice before accepting it. Both decoders
    // deliver several reads a second, so the wait is imperceptible.
    let lastCode = null;
    let repeats  = 0;
    let accepted = false;

    function offer(raw) {
      if (accepted) return;
      const code = String(raw ?? '').replace(/\D/g, '');
      if (!isBookEan(code)) {
        if (code.length === 13) {
          ui.status.textContent = 'That barcode is not an ISBN — scan the one starting 978 or 979.';
        }
        return;
      }
      repeats = code === lastCode ? repeats + 1 : 1;
      lastCode = code;
      if (repeats < 2) return;

      // Hold the read on screen for a moment — a buzz, a green frame and the
      // digits — so a scan that worked looks different from one the camera
      // simply never got.
      accepted = true;
      ui.status.textContent = code;
      ui.el.classList.add('scanner--hit');
      navigator.vibrate?.(60);
      setTimeout(() => settle({ isbn: code }), 250);
    }

    function setupTorch() {
      const track = stream?.getVideoTracks()[0];
      if (!track?.getCapabilities) return;
      let on = false;
      try {
        if (!track.getCapabilities().torch) return;
      } catch { return; }
      ui.torch.hidden = false;
      ui.torch.addEventListener('click', async () => {
        on = !on;
        try {
          await track.applyConstraints({ advanced: [{ torch: on }] });
          ui.torch.classList.toggle('scanner__torch--on', on);
        } catch { ui.torch.hidden = true; }
      });
    }

    // A phone's rear camera autofocuses, so a barcode held close is both big
    // and sharp and 720p is plenty. A laptop webcam is fixed-focus, sharp only
    // past roughly 30 cm, and at that distance an EAN-13 covers about a tenth
    // of the frame — some 130 px of bars at 720p, under the ~150–200 px the
    // decoder needs. Pixels are the only lever left, so ask a camera that
    // isn't a rear one for as much as it has: the same framing then gives
    // ~190 px, which does decode. Phones are left at 720p, where they already
    // work and where each frame is quicker to scan.
    function cameraConstraints(preferRear) {
      return {
        video: {
          facingMode: { ideal: 'environment' },
          width:  { ideal: preferRear ? 1280 : 1920 },
          height: { ideal: preferRear ? 720  : 1080 },
        },
      };
    }

    // Reopen a non-rear camera at the highest resolution it will give. Done
    // before any decoding starts: ZXing sizes its capture canvas off the first
    // frame it sees and keeps it, so a resolution change afterwards would be
    // cropped away.
    async function upgradeIfWebcam() {
      const track = stream?.getVideoTracks()[0];
      const settings = track?.getSettings?.() ?? {};
      if (settings.facingMode === 'environment') return false;
      try {
        await track.applyConstraints(cameraConstraints(false).video);
      } catch { /* the camera has nothing better to give */ }
      return true;
    }

    (async () => {
      try {
        const detector = await nativeDetector();

        if (!detector) {
          // Load the decoder before opening the camera, so the permission
          // prompt isn't followed by a black preview while 360 KB downloads.
          ui.status.textContent = 'Loading scanner…';
          const ZXing = await loadZXing();
          if (done) return;

          // EAN-13 only: restricting the formats keeps each attempt cheap and
          // rules out a QR code elsewhere on the cover. TRY_HARDER scans the
          // whole frame instead of a band across the middle and retries
          // rotated, which is what makes a hand-held phone forgiving.
          const hints = new Map([
            [ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.EAN_13]],
            [ZXing.DecodeHintType.TRY_HARDER, true],
          ]);
          reader = new ZXing.BrowserMultiFormatReader(hints, DECODE_INTERVAL_MS);
          reader.timeBetweenDecodingAttempts = DECODE_INTERVAL_MS;
        }

        stream = await navigator.mediaDevices.getUserMedia(cameraConstraints(true));
        if (done) { stream.getTracks().forEach(t => t.stop()); return; }
        const isWebcam = await upgradeIfWebcam();
        if (done) { stream.getTracks().forEach(t => t.stop()); return; }

        if (detector) {
          ui.video.srcObject = stream;
          await ui.video.play().catch(() => {});   // muted + inline: allowed
          let last = 0;
          const tick = async ts => {
            if (done) return;
            if (ts - last >= DECODE_INTERVAL_MS) {
              last = ts;
              try {
                for (const code of await detector.detect(ui.video)) offer(code.rawValue);
              } catch { /* a frame the detector could not read */ }
            }
            if (!done) rafId = requestAnimationFrame(tick);
          };
          rafId = requestAnimationFrame(tick);
        } else {
          await reader.decodeFromStream(stream, ui.video, result => {
            if (result) offer(result.getText());
          });
          if (done) { reader.reset(); return; }
        }

        ui.status.textContent = isWebcam
          ? 'Hold the book where the preview looks sharp, filling the frame — webcams rarely focus closer than about 30 cm'
          : 'Point the camera at the barcode on the back cover';
        setupTorch();
      } catch (err) {
        console.error(err);
        settle({ error: err?.message === 'ZXing did not load'
          ? 'Could not load the barcode scanner — check your connection.'
          : cameraError(err) });
      }
    })();
  });
}
