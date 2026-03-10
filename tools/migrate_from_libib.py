#!/usr/bin/env python3
"""
libib_migrate.py — Convert a Libib CSV export to Biblio format.

Produces:
  - data/books.json          (one entry per book: isbn, title, author, year, cover)
  - data/books/<isbn>.json  (full metadata per book)
  - covers/                 (empty dir, populated later by cover fetch)
  - migration_report.txt    (summary + rows that need attention)

Usage:
  python3 libib_migrate.py libib_export.csv [--out ./output]

Requirements:
  pip install tqdm   (optional, for progress bar)
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ── Libib CSV columns we actually use ────────────────────────────────────────

FIELD_ITEM_TYPE   = "item_type"
FIELD_TITLE       = "title"
FIELD_CREATORS    = "creators"
FIELD_FIRST_NAME  = "first_name"
FIELD_LAST_NAME   = "last_name"
FIELD_ISBN13      = "ean_isbn13"
FIELD_ISBN10      = "upc_isbn10"
FIELD_DESCRIPTION = "description"
FIELD_PUBLISHER   = "publisher"
FIELD_PUBLISH_DATE= "publish_date"
FIELD_TAGS        = "tags"
FIELD_NOTES       = "notes"
FIELD_LENGTH      = "length"       # page count for books
FIELD_STATUS      = "status"
FIELD_BEGAN       = "began"
FIELD_COMPLETED   = "completed"
FIELD_ADDED       = "added"
FIELD_COPIES      = "copies"
FIELD_RATING      = "rating"
FIELD_REVIEW      = "review"

# ── Helpers ───────────────────────────────────────────────────────────────────

def clean(s):
    """Strip whitespace, return None for empty strings."""
    if s is None:
        return None
    s = s.strip()
    return s if s else None

def parse_year(date_str):
    """Extract year from YYYY-MM-DD or YYYY strings."""
    if not date_str:
        return None
    m = re.match(r'(\d{4})', date_str.strip())
    return int(m.group(1)) if m else None

def normalize_isbn(isbn13, isbn10):
    """Return the best available ISBN as a plain string."""
    for candidate in [isbn13, isbn10]:
        v = clean(candidate)
        if v:
            # Strip any non-digit characters (hyphens, spaces)
            v = re.sub(r'[^\dX]', '', v, flags=re.IGNORECASE)
            if len(v) in (10, 13):
                return v
    return None

def normalize_author(creators, first_name, last_name):
    """Return the best author string available."""
    c = clean(creators)
    if c:
        return c
    parts = [clean(first_name), clean(last_name)]
    joined = " ".join(p for p in parts if p)
    return joined if joined else None

def parse_subjects(tags):
    """Split comma/semicolon-separated tags into a list."""
    if not tags:
        return []
    return [t.strip() for t in re.split(r'[,;]', tags) if t.strip()]

def cover_path(isbn):
    return f"covers/{isbn}.webp"

# ── Row converter ─────────────────────────────────────────────────────────────

def convert_row(row, row_num):
    """
    Convert one Libib CSV row to (grid_entry, detail_entry, warning).
    Returns (None, None, reason) if the row should be skipped.
    """
    # Only process books
    item_type = clean(row.get(FIELD_ITEM_TYPE, ""))
    if item_type and item_type.lower() != "book":
        return None, None, f"skipped (item_type={item_type!r})"

    title = clean(row.get(FIELD_TITLE))
    if not title:
        return None, None, "skipped (no title)"

    isbn = normalize_isbn(
        row.get(FIELD_ISBN13, ""),
        row.get(FIELD_ISBN10, "")
    )

    author  = normalize_author(
        row.get(FIELD_CREATORS, ""),
        row.get(FIELD_FIRST_NAME, ""),
        row.get(FIELD_LAST_NAME, "")
    )
    year    = parse_year(row.get(FIELD_PUBLISH_DATE, ""))
    warning = None

    if not isbn:
        # Use a slug as fallback key — won't have a cover or be linkable
        slug = re.sub(r'[^a-z0-9]', '_', title.lower())[:40]
        isbn = f"noisbn_{slug}"
        warning = f"row {row_num}: no ISBN — using slug key: {isbn!r}"

    added = clean(row.get(FIELD_ADDED))

    grid_entry = {
        "isbn":   isbn,
        "title":  title,
        "author": author or "",
        "year":   year,
        "cover":  cover_path(isbn),
    }
    if added:
        grid_entry["added"] = added

    # Pages: Libib stores it in 'length'
    pages_raw = clean(row.get(FIELD_LENGTH))
    pages = int(pages_raw) if pages_raw and pages_raw.isdigit() else None

    detail_entry = {
        "isbn":        isbn,
        "title":       title,
        "author":      author or "",
        "year":        year,
        "cover":       cover_path(isbn),
        "publisher":   clean(row.get(FIELD_PUBLISHER)),
        "pages":       pages,
        "language":    None,   # Libib doesn't export language
        "description": clean(row.get(FIELD_DESCRIPTION)),
        "subjects":    parse_subjects(row.get(FIELD_TAGS, "")),
        "notes":       clean(row.get(FIELD_NOTES)),
        "copies":      int(c) if (c := clean(row.get(FIELD_COPIES, ""))) and c.isdigit() else 1,
        "status":      clean(row.get(FIELD_STATUS)),
        "rating":      clean(row.get(FIELD_RATING)),
        "review":      clean(row.get(FIELD_REVIEW)),
        "addedAt":     clean(row.get(FIELD_ADDED)),
        "source":      "libib",
    }

    # Remove None values to keep files lean
    detail_entry = {k: v for k, v in detail_entry.items() if v is not None}

    return grid_entry, detail_entry, warning

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Migrate Libib CSV to Biblio format.")
    parser.add_argument("csv_file", help="Path to the Libib CSV export")
    parser.add_argument("--out", default="./Biblio_import",
                        help="Output directory (default: ./Biblio_import)")
    args = parser.parse_args()

    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"Error: file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    books_dir = out_dir / "data" / "books"
    covers_dir = out_dir / "covers"
    books_dir.mkdir(parents=True, exist_ok=True)
    covers_dir.mkdir(parents=True, exist_ok=True)

    # Try tqdm if available
    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False

    grid   = []
    warnings = []
    skipped  = []
    seen_isbns = set()
    duplicates = []

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=',', quotechar='"')
        rows = list(reader)

    print(f"Read {len(rows)} rows from {csv_path.name}")

    iterator = tqdm(enumerate(rows, 1), total=len(rows)) if use_tqdm else enumerate(rows, 1)

    for row_num, row in iterator:
        grid_entry, detail_entry, warning = convert_row(row, row_num)

        if grid_entry is None:
            skipped.append(f"row {row_num}: {warning}")
            continue

        if warning:
            warnings.append(warning)

        isbn = grid_entry["isbn"]

        # Duplicate ISBN handling: keep first, log the rest
        if isbn in seen_isbns:
            duplicates.append(
                f"row {row_num}: duplicate ISBN {isbn!r} for \"{grid_entry['title']}\" — skipped"
            )
            continue

        seen_isbns.add(isbn)
        grid.append(grid_entry)

        # Write per-book detail JSON
        detail_path = books_dir / f"{isbn}.json"
        with open(detail_path, "w", encoding="utf-8") as f:
            json.dump(detail_entry, f, ensure_ascii=False, indent=2)

    # Write books.json
    grid_path = out_dir / "data" / "books.json"
    with open(grid_path, "w", encoding="utf-8") as f:
        json.dump(grid, f, ensure_ascii=False, indent=2)

    # ── Report ────────────────────────────────────────────────────────────────
    report_lines = [
        "Biblio Migration Report",
        "=" * 40,
        f"Generated:    {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Source:       {csv_path.name}",
        f"Input rows:   {len(rows)}",
        f"Imported:     {len(grid)}",
        f"Skipped:      {len(skipped)}",
        f"Duplicates:   {len(duplicates)}",
        f"Warnings:     {len(warnings)}",
        "",
        "── No ISBN (slug key used) ──",
        *([w for w in warnings] or ["  none"]),
        "",
        "── Duplicates ──",
        *([d for d in duplicates] or ["  none"]),
        "",
        "── Skipped rows ──",
        *([s for s in skipped] or ["  none"]),
        "",
        "── Next steps ──",
        "1. Copy data/ and covers/ into your Biblio repo.",
        "2. For books with slug keys (no ISBN), find ISBNs manually and rename",
        "   both the JSON file and the entry in books.json.",
        "3. Run a cover fetch pass — e.g. fetch covers from Open Library for",
        "   each ISBN in books.json and save as covers/<isbn>.webp.",
        "4. git add . && git commit -m 'import from libib' && git push",
        ]

    report_path = out_dir / "migration_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    # Console summary
    print()
    print("── Migration complete ──────────────────")
    print(f"  Imported:   {len(grid)} books")
    print(f"  Skipped:    {len(skipped)}")
    print(f"  Duplicates: {len(duplicates)}")
    print(f"  Warnings:   {len(warnings)}")
    print()
    print(f"  Output:  {out_dir.resolve()}/")
    print(f"    data/books.json          ({len(grid)} entries)")
    print(f"    data/books/<isbn>.json  ({len(grid)} files)")
    print(f"    covers/                 (empty — populate with cover fetch)")
    print(f"    migration_report.txt")
    print()
    if warnings:
        print(f"  ⚠  {len(warnings)} books have no ISBN — check migration_report.txt")


if __name__ == "__main__":
    main()
