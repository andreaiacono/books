#!/usr/bin/env python3
"""
fetch_covers.py — Download book cover images for all entries in grid.json.

Source:
  Google Books API  (https://www.googleapis.com/books/v1)

Saves covers as JPEG (renamed .webp — browsers don't care about the extension,
and converting to real WebP requires Pillow with WebP support; see --convert flag).

Usage:
  python3 fetch_covers.py [--grid data/grid.json] [--out covers/] [options]

Options:
  --grid PATH       Path to grid.json          (default: data/grid.json)
  --out DIR         Output directory           (default: covers/)
  --delay SECONDS   Pause between requests     (default: 0.5)
  --convert         Convert to real WebP via Pillow (requires: pip install Pillow)
  --skip-existing   Skip ISBNs that already have a cover file (default: true)
  --force           Re-download even if cover already exists
  --limit N         Only process first N books (useful for testing)

Requirements:
  pip install requests tqdm          (tqdm optional, for progress bar)
  pip install Pillow                 (only needed for --convert)
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

# ── Sources ───────────────────────────────────────────────────────────────────

def fetch_google_thumbnail(isbn, session, api_key=None):
    """Ask Google Books API for the thumbnail URL, then fetch that image."""
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        if api_key:
            url += f"&key={api_key}"
        r = session.get(url, timeout=10)
        if r.status_code == 429:
            raise RuntimeError("Google Books API quota exceeded — pass --api-key to use your own quota")
        if r.status_code == 403:
            raise RuntimeError("Google Books API access denied — check your API key")
        r.raise_for_status()
        data = r.json()
        if data.get("totalItems", 0) == 0:
            return None
        links = data["items"][0].get("volumeInfo", {}).get("imageLinks", {})
        # Prefer largest available
        for key in ("extraLarge", "large", "medium", "thumbnail"):
            img_url = links.get(key)
            if img_url:
                # Force https and remove zoom restriction
                img_url = img_url.replace("http://", "https://").replace("&edge=curl", "")
                r2 = session.get(img_url, timeout=10)
                r2.raise_for_status()
                if len(r2.content) > 1000:   # ignore 1×1 placeholder responses
                    return r2.content
    except Exception:
        pass
    return None

# ── Conversion ────────────────────────────────────────────────────────────────

def convert_to_webp(data: bytes, quality: int = 82) -> bytes:
    """Convert image bytes to real WebP using Pillow."""
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(data)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality, method=6)
    return buf.getvalue()

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch book covers for BiblioTrack.")
    parser.add_argument("--grid",    default="data/grid.json", help="Path to grid.json")
    parser.add_argument("--out",     default="covers",         help="Output directory")
    parser.add_argument("--delay",   type=float, default=0.5,  help="Seconds between requests")
    parser.add_argument("--api-key", default=None,             help="Google Books API key (avoids shared quota limits)")
    parser.add_argument("--convert", action="store_true",      help="Convert to real WebP (needs Pillow)")
    parser.add_argument("--force",   action="store_true",      help="Re-download existing covers")
    parser.add_argument("--limit",   type=int, default=None,   help="Process only first N books")
    args = parser.parse_args()

    grid_path = Path(args.grid)
    out_dir   = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not grid_path.exists():
        print(f"Error: {grid_path} not found.", file=sys.stderr)
        sys.exit(1)

    with open(grid_path, encoding="utf-8") as f:
        grid = json.load(f)

    if args.limit:
        grid = grid[:args.limit]

    # Filter out slug-only entries (no real ISBN)
    real = [b for b in grid if not b["isbn"].startswith("noisbn_")]
    fake = [b for b in grid if b["isbn"].startswith("noisbn_")]

    if fake:
        print(f"  Skipping {len(fake)} entries with no ISBN (slug keys).")

    # Separate already-covered from pending
    if not args.force:
        pending  = [b for b in real if not (out_dir / f"{b['isbn']}.webp").exists()]
        existing = len(real) - len(pending)
        if existing:
            print(f"  {existing} covers already present — skipping (use --force to re-download).")
    else:
        pending = real

    print(f"  {len(pending)} covers to fetch.\n")

    if not pending:
        print("Nothing to do.")
        return

    # Try tqdm
    try:
        from tqdm import tqdm
        iterator = tqdm(pending, unit="book")
    except ImportError:
        iterator = pending

    session = requests.Session()
    session.headers["User-Agent"] = "BiblioTrack/1.0 (cover fetch; +https://github.com)"

    stats = {"ok": 0, "missing": 0, "error": 0}
    missing = []

    for book in iterator:
        isbn  = book["isbn"]
        title = book.get("title", isbn)
        dest  = out_dir / f"{isbn}.webp"

        try:
            data = fetch_google_thumbnail(isbn, session, args.api_key)
            if data:
                stats["ok"] += 1
                if args.convert:
                    try:
                        data = convert_to_webp(data)
                    except Exception as e:
                        pass   # save as JPEG anyway, extension is still .webp

                dest.write_bytes(data)
                if hasattr(iterator, "set_postfix"):
                    iterator.set_postfix(src="GB", isbn=isbn[-4:])
            else:
                stats["missing"] += 1
                missing.append({"isbn": isbn, "title": title})
                if hasattr(iterator, "set_postfix"):
                    iterator.set_postfix(src="—", isbn=isbn[-4:])

        except Exception as e:
            stats["error"] += 1
            missing.append({"isbn": isbn, "title": title, "error": str(e)})

        time.sleep(args.delay)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n── Cover fetch complete ────────────────")
    print(f"  Found:         {stats['ok']}  (Google Books)")
    print(f"  Not found:     {stats['missing']}")
    print(f"  Errors:        {stats['error']}")

    if missing:
        missing_path = out_dir / "missing_covers.json"
        with open(missing_path, "w", encoding="utf-8") as f:
            json.dump(missing, f, ensure_ascii=False, indent=2)
        print(f"\n  ISBNs with no cover saved to: {missing_path}")
        print(f"  You can search for these manually on:")
        print(f"    https://www.amazon.com/dp/<ISBN10>")

    print()


if __name__ == "__main__":
    main()

# run with
# Test on first 20 books before committing to the full run
# python3 fetch_covers.py --limit 20

# Re-run safely after an interruption — already-downloaded covers are skipped
# python3 fetch_covers.py

# Force re-download everything (e.g. you want larger images)
# python3 fetch_covers.py --force --size L