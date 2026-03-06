#!/usr/bin/env python3
"""
fetch_descriptions.py — Back-fill book descriptions from Google Books / Open Library.

For each data/books/{isbn}.json that lacks a description, tries:
  1. Google Books API  (usually returns description in the book's own language)
  2. Open Library API  (fallback)

Updates JSON files in place.

Usage:
  python3 fetch_descriptions.py [--books-dir ../data/books] [--force] [--dry-run]

Options:
  --books-dir DIR   Path to data/books/ directory (default: ../data/books relative to this script)
  --skip-existing   Skip books that already have a description
  --dry-run         Show what would be fetched without writing anything
  --delay SECS      Seconds to wait between API calls (default: 0.5)

Requirements:
  pip install requests tqdm   (tqdm is optional)
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: 'requests' is required. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


# ── API fetchers ──────────────────────────────────────────────────────────────

def fetch_google_books(isbn: str, session: requests.Session) -> str | None:
    """Return description from Google Books, or None."""
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", [])
        if not items:
            return None
        desc = items[0].get("volumeInfo", {}).get("description")
        return desc.strip() if desc and desc.strip() else None
    except Exception:
        return None


def fetch_open_library(isbn: str, session: requests.Session) -> str | None:
    """Return description from Open Library, or None."""
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        entry = data.get(f"ISBN:{isbn}", {})
        desc = entry.get("notes") or entry.get("description")
        # description can be a string or {"type": ..., "value": ...}
        if isinstance(desc, dict):
            desc = desc.get("value")
        return desc.strip() if desc and desc.strip() else None
    except Exception:
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = Path(__file__).parent
    default_books_dir = script_dir.parent / "data" / "books"

    parser = argparse.ArgumentParser(description="Fetch missing book descriptions.")
    parser.add_argument("--books-dir", type=Path, default=default_books_dir,
                        help=f"Path to data/books/ (default: {default_books_dir})")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip books that already have a description")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without writing files")
    parser.add_argument("--delay", type=float, default=2,
                        help="Seconds between API calls (default: 2)")
    args = parser.parse_args()

    books_dir = args.books_dir
    if not books_dir.is_dir():
        print(f"Error: directory not found: {books_dir}", file=sys.stderr)
        sys.exit(1)

    all_files = sorted(books_dir.glob("*.json"))
    print(f"Found {len(all_files)} book files in {books_dir}")

    # Filter to those needing a description
    to_process = []
    for path in all_files:
        with open(path, encoding="utf-8") as f:
            book = json.load(f)
        has_desc = bool(book.get("description", "").strip() if isinstance(book.get("description"), str) else book.get("description"))
        if not has_desc or not args.skip_existing:
            to_process.append((path, book))

    skipped_count = len(all_files) - len(to_process)
    if skipped_count:
        print(f"  {skipped_count} already have a description (skipped, --skip-existing)")
    print(f"  {len(to_process)} to fetch")
    if args.dry_run:
        print("  [dry-run] no files will be written")
    print()

    if not to_process:
        print("Nothing to do.")
        return

    session = requests.Session()
    session.headers.update({"User-Agent": "Biblio/1.0 (personal library; fetch_descriptions)"})

    results = {"fetched_google": 0, "fetched_ol": 0, "not_found": 0, "errors": []}

    iterator = tqdm(to_process) if HAS_TQDM else to_process

    for path, book in iterator:
        isbn = book.get("isbn", path.stem)
        title = book.get("title", "?")

        label = f"[{isbn}] {title[:50]}"

        # 1. Google Books
        desc = fetch_google_books(isbn, session)
        source = "google"
        time.sleep(args.delay)

        # 2. Open Library fallback
        if not desc:
            desc = fetch_open_library(isbn, session)
            source = "openlibrary"
            time.sleep(args.delay)

        if not desc:
            results["not_found"] += 1
            if not HAS_TQDM:
                print(f"  NOT FOUND  {label}")
            continue

        if not HAS_TQDM:
            src_tag = "Google" if source == "google" else "OL    "
            print(f"  {src_tag}  {label}")

        if source == "google":
            results["fetched_google"] += 1
        else:
            results["fetched_ol"] += 1

        if not args.dry_run:
            book["description"] = desc
            with open(path, "w", encoding="utf-8") as f:
                json.dump(book, f, ensure_ascii=False, indent=2)

    print()
    print("── Done ────────────────────────────────────────")
    print(f"  From Google Books:  {results['fetched_google']}")
    print(f"  From Open Library:  {results['fetched_ol']}")
    print(f"  Not found:          {results['not_found']}")
    if args.dry_run:
        print("  [dry-run] no files were written")


if __name__ == "__main__":
    main()