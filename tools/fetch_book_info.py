#!/usr/bin/env python3
"""
fetch_book_info.py — Back-fill missing book metadata from Google Books / Open Library.

For each data/books/{isbn}.json, fills in any missing fields from:
  - description
  - author
  - publisher
  - pages
  - subjects

Tries:
  1. Google Books API  (usually returns data in the book's own language)
  2. Open Library API  (fallback)

Updates JSON files in place. Tracks completed ISBNs in a progress file so runs
can be safely interrupted and resumed — already-processed books are skipped.
Detects Google Books quota exhaustion (HTTP 429) and stops calling that API for
the rest of the session, falling back to Open Library only.

Usage:
  python3 fetch_book_info.py [--books-dir ../data/books] [--skip-existing] [--dry-run]

Options:
  --books-dir DIR      Path to data/books/ directory (default: ../data/books relative to this script)
  --progress-file FILE Path to progress JSON file (default: fetch_progress.json next to this script)
  --reset-progress     Ignore the existing progress file and start fresh
  --skip-existing      Skip books where ALL target fields are already populated
  --force              Overwrite fields even if they are already present
  --dry-run            Show what would happen without writing anything
  --delay SECS         Seconds to wait between API calls (default: 2)
  --fields FIELDS      Comma-separated list of fields to fill (default: all)
                       Choices: description,author,publisher,pages,subjects

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


ALL_FIELDS = {"description", "author", "publisher", "pages", "subjects"}

GOOGLE_QUOTA_CODES = {429, 403}  # 403 can also signal quota exhaustion


# ── Progress file ─────────────────────────────────────────────────────────────

def load_progress(progress_file: Path) -> set:
    """Return the set of ISBNs already successfully processed."""
    if not progress_file.exists():
        return set()
    try:
        with open(progress_file, encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("completed", []))
    except Exception:
        print(f"  Warning: could not read progress file {progress_file}, starting fresh.",
              file=sys.stderr)
        return set()


def save_progress(progress_file: Path, completed: set) -> None:
    """Persist the set of completed ISBNs atomically."""
    tmp = progress_file.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"completed": sorted(completed)}, f, indent=2)
    tmp.replace(progress_file)


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_missing(book: dict, field: str) -> bool:
    """Return True if the field is absent or effectively empty."""
    val = book.get(field)
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip()
    if isinstance(val, list):
        return len(val) == 0
    if isinstance(val, int):
        return val <= 0
    return False


def fields_needed(book: dict, target_fields: set, force: bool = False) -> set:
    """Return the subset of target_fields that are missing from book.
    If force is True, return all target_fields regardless of current values."""
    if force:
        return set(target_fields)
    return {f for f in target_fields if is_missing(book, f)}


# ── API fetchers ──────────────────────────────────────────────────────────────

class GoogleQuotaExceeded(Exception):
    """Raised when Google Books signals quota exhaustion."""


def fetch_google_books(isbn: str, session: requests.Session) -> dict:
    """
    Return a dict with any available fields from Google Books.
    Keys present only when data was found: description, author, publisher, pages, subjects.
    Raises GoogleQuotaExceeded if the API returns a quota / rate-limit error.
    """
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    result = {}
    try:
        r = session.get(url, timeout=10)
        if r.status_code in GOOGLE_QUOTA_CODES:
            raise GoogleQuotaExceeded(
                f"Google Books returned HTTP {r.status_code} — quota likely exhausted."
            )
        r.raise_for_status()
        data = r.json()
        # Google also embeds quota errors in a 200 response body
        if "error" in data:
            err = data["error"]
            if err.get("code") in GOOGLE_QUOTA_CODES or "quota" in str(err).lower():
                raise GoogleQuotaExceeded(f"Google Books error: {err.get('message', err)}")
        items = data.get("items", [])
        if not items:
            return result
        info = items[0].get("volumeInfo", {})

        if desc := info.get("description", "").strip():
            result["description"] = desc

        authors = info.get("authors", [])
        if authors:
            result["author"] = ", ".join(authors)

        if publisher := info.get("publisher", "").strip():
            result["publisher"] = publisher

        if pages := info.get("pageCount"):
            if isinstance(pages, int) and pages > 0:
                result["pages"] = pages

        categories = info.get("categories", [])
        if categories:
            # Google returns broad categories like "Business & Economics / General"
            # Flatten and deduplicate
            subjects = []
            seen = set()
            for cat in categories:
                for part in cat.split("/"):
                    part = part.strip()
                    if part and part.lower() not in seen:
                        subjects.append(part)
                        seen.add(part.lower())
            if subjects:
                result["subjects"] = subjects

    except GoogleQuotaExceeded:
        raise
    except Exception:
        pass
    return result


def fetch_open_library(isbn: str, session: requests.Session) -> dict:
    """
    Return a dict with any available fields from Open Library.
    Keys present only when data was found: description, author, publisher, pages, subjects.
    """
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    result = {}
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        entry = data.get(f"ISBN:{isbn}", {})
        if not entry:
            return result

        # Description
        desc = entry.get("notes") or entry.get("description")
        if isinstance(desc, dict):
            desc = desc.get("value")
        if desc and isinstance(desc, str) and desc.strip():
            result["description"] = desc.strip()

        # Author
        authors = entry.get("authors", [])
        if authors:
            names = [a.get("name", "").strip() for a in authors if a.get("name")]
            if names:
                result["author"] = ", ".join(names)

        # Publisher
        publishers = entry.get("publishers", [])
        if publishers:
            name = publishers[0].get("name", "").strip()
            if name:
                result["publisher"] = name

        # Pages
        pages = entry.get("number_of_pages")
        if isinstance(pages, int) and pages > 0:
            result["pages"] = pages

        # Subjects
        subjects_raw = entry.get("subjects", [])
        subjects = []
        seen = set()
        for s in subjects_raw:
            name = s.get("name", "").strip() if isinstance(s, dict) else str(s).strip()
            if name and name.lower() not in seen:
                subjects.append(name)
                seen.add(name.lower())
        if subjects:
            result["subjects"] = subjects

    except Exception:
        pass
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = Path(__file__).parent
    default_books_dir = script_dir.parent / "data" / "books"
    default_progress_file = script_dir / "fetch_progress.json"

    parser = argparse.ArgumentParser(description="Fetch missing book metadata fields.")
    parser.add_argument("--books-dir", type=Path, default=default_books_dir,
                        help=f"Path to data/books/ (default: {default_books_dir})")
    parser.add_argument("--progress-file", type=Path, default=default_progress_file,
                        help=f"Path to progress file (default: {default_progress_file})")
    parser.add_argument("--reset-progress", action="store_true",
                        help="Ignore existing progress file and start fresh")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip books where ALL target fields are already populated")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite fields even if they are already present")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without writing files")
    parser.add_argument("--delay", type=float, default=2,
                        help="Seconds between API calls (default: 2)")
    parser.add_argument("--fields", type=str, default=",".join(sorted(ALL_FIELDS)),
                        help=f"Comma-separated fields to fill (default: all). "
                             f"Choices: {', '.join(sorted(ALL_FIELDS))}")
    args = parser.parse_args()

    # --force and --skip-existing are mutually exclusive
    if args.force and args.skip_existing:
        print("Error: --force and --skip-existing are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    # Parse target fields
    requested = {f.strip().lower() for f in args.fields.split(",")}
    invalid = requested - ALL_FIELDS
    if invalid:
        print(f"Error: unknown field(s): {', '.join(sorted(invalid))}. "
              f"Valid: {', '.join(sorted(ALL_FIELDS))}", file=sys.stderr)
        sys.exit(1)
    target_fields = requested
    print(f"Target fields: {', '.join(sorted(target_fields))}")
    if args.force:
        print("  [force] existing field values will be overwritten")

    books_dir = args.books_dir
    if not books_dir.is_dir():
        print(f"Error: directory not found: {books_dir}", file=sys.stderr)
        sys.exit(1)

    # Load progress (force skips the progress file to re-process everything)
    progress_file = args.progress_file
    if args.reset_progress or args.force:
        completed_isbns: set = set()
        if args.force:
            print("Progress file ignored — force mode re-processes all books.")
        else:
            print("Progress file reset — processing all books.")
    else:
        completed_isbns = load_progress(progress_file)
        if completed_isbns:
            print(f"Resuming: {len(completed_isbns)} ISBNs already done (from {progress_file})")

    all_files = sorted(books_dir.glob("*.json"))
    print(f"Found {len(all_files)} book files in {books_dir}")

    # Filter to those needing at least one field, and not already completed
    to_process = []
    for path in all_files:
        with open(path, encoding="utf-8") as f:
            book = json.load(f)
        isbn = book.get("isbn", path.stem)
        if isbn in completed_isbns:
            continue
        missing = fields_needed(book, target_fields, force=args.force)
        if missing or not args.skip_existing:
            to_process.append((path, book, missing))

    skipped_progress = len(completed_isbns)
    skipped_complete = len(all_files) - len(to_process) - skipped_progress
    if skipped_progress:
        print(f"  {skipped_progress} skipped (already in progress file)")
    if skipped_complete > 0:
        print(f"  {skipped_complete} already complete (--skip-existing)")
    print(f"  {len(to_process)} to process")
    if args.dry_run:
        print("  [dry-run] no files will be written")
    print()

    if not to_process:
        print("Nothing to do.")
        return

    session = requests.Session()
    session.headers.update({"User-Agent": "Biblio/1.0 (personal library; fetch_metadata)"})

    # Track per-field fill counts
    fill_counts = {f: 0 for f in target_fields}
    overwrite_counts = {f: 0 for f in target_fields}
    not_found_count = 0
    google_quota_hit = False

    iterator = tqdm(to_process) if HAS_TQDM else to_process

    for path, book, missing_fields in iterator:
        isbn = book.get("isbn", path.stem)
        title = book.get("title", "?")
        label = f"[{isbn}] {title[:50]}"

        if not missing_fields:
            # --skip-existing was NOT set, but nothing is actually missing
            if not HAS_TQDM:
                print(f"  COMPLETE   {label}")
            if not args.dry_run:
                completed_isbns.add(isbn)
                save_progress(progress_file, completed_isbns)
            continue

        # 1. Google Books (unless quota already exhausted this session)
        google_data = {}
        if not google_quota_hit:
            try:
                google_data = fetch_google_books(isbn, session)
                time.sleep(args.delay)
            except GoogleQuotaExceeded as e:
                google_quota_hit = True
                print(f"\n  ⚠  GOOGLE QUOTA EXCEEDED: {e}")
                print("     Switching to Open Library only for remaining books.\n")

        # 2. Open Library (always as fallback, or exclusively if quota hit)
        still_missing = missing_fields - set(google_data.keys())
        ol_data = {}
        if still_missing:
            ol_data = fetch_open_library(isbn, session)
            time.sleep(args.delay)

        # Merge: Google takes priority, OL fills the rest
        filled = {}
        for field in missing_fields:
            if field in google_data:
                filled[field] = google_data[field]
            elif field in ol_data:
                filled[field] = ol_data[field]

        if not filled:
            not_found_count += 1
            if not HAS_TQDM:
                print(f"  NOT FOUND  {label}  (missing: {', '.join(sorted(missing_fields))})")
            # Still mark as visited so we don't retry endlessly
            if not args.dry_run:
                completed_isbns.add(isbn)
                save_progress(progress_file, completed_isbns)
            continue

        filled_names = ", ".join(sorted(filled.keys()))
        if not HAS_TQDM:
            src = " [OL only]" if google_quota_hit else ""
            mode = " [force]" if args.force else ""
            print(f"  FILLED{src}{mode:<9}{label}  ({filled_names})")

        for field in filled:
            if args.force and not is_missing(book, field):
                overwrite_counts[field] += 1
            else:
                fill_counts[field] += 1

        if not args.dry_run:
            book.update(filled)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(book, f, ensure_ascii=False, indent=2)
            completed_isbns.add(isbn)
            save_progress(progress_file, completed_isbns)

    print()
    print("── Done ────────────────────────────────────────")
    for field in sorted(fill_counts):
        line = f"  {field:<14} filled: {fill_counts[field]}"
        if args.force and overwrite_counts[field]:
            line += f"  (overwritten: {overwrite_counts[field]})"
        print(line)
    print(f"  {'not found':<14}        {not_found_count}")
    if google_quota_hit:
        print("  ⚠  Google Books quota was exhausted during this run.")
        print("     Re-run tomorrow to retry with Google for remaining books.")
        print(f"     Progress saved to: {progress_file}")
    if args.dry_run:
        print("  [dry-run] no files were written")


if __name__ == "__main__":
    main()