#!/usr/bin/env python3
"""
Sync book detail files into the recap JSON.

Usage:
    python sync_books.py --details-dir <dir> --recap <file> [--output <file>]

Arguments:
    --details-dir   Directory containing individual book JSON files (default: ./books)
    --recap         Path to the recap JSON array file (default: ./recap.json)
    --output        Where to write the updated recap (default: overwrites recap file)
"""

import json
import argparse
from pathlib import Path

# Fields that may be present in detail files but missing from recap entries.
# Mapped as: detail_field -> recap_field (use same name if identical).
FIELDS_TO_SYNC = {
    "author": "author",
    "year": "year",
}


def load_json(path: Path) -> any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def sync(details_dir: Path, recap_path: Path, output_path: Path) -> None:
    # Load recap array
    recap: list[dict] = load_json(recap_path)

    # Build a lookup from isbn -> index for fast access
    isbn_to_index: dict[str, int] = {
        book["isbn"]: i for i, book in enumerate(recap)
    }

    # Collect all detail files
    detail_files = sorted(details_dir.glob("*.json"))
    if not detail_files:
        print(f"No JSON files found in '{details_dir}'.")
        return

    updated_count = 0
    field_stats: dict[str, int] = {f: 0 for f in FIELDS_TO_SYNC.values()}

    for detail_path in detail_files:
        detail = load_json(detail_path)
        isbn = detail.get("isbn")

        if not isbn:
            print(f"  [SKIP] {detail_path.name}: no 'isbn' field.")
            continue

        if isbn not in isbn_to_index:
            print(f"  [SKIP] {isbn}: not found in recap.")
            continue

        idx = isbn_to_index[isbn]
        recap_book = recap[idx]
        changed = False

        for detail_field, recap_field in FIELDS_TO_SYNC.items():
            if detail_field in detail and not recap_book.get(recap_field):
                recap_book[recap_field] = detail[detail_field]
                field_stats[recap_field] += 1
                changed = True

        if changed:
            updated_count += 1
            print(f"  [UPDATED] {isbn} — {recap_book.get('title', '')}")

    # Write result
    save_json(output_path, recap)

    print(f"\nDone. {updated_count}/{len(detail_files)} books updated.")
    print("Fields added:")
    for field, count in field_stats.items():
        print(f"  {field}: {count}")
    print(f"Saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Sync book details into recap JSON.")
    parser.add_argument("--details-dir", default="books",
                        help="Directory with individual book JSON files (default: ./books)")
    parser.add_argument("--recap", default="recap.json",
                        help="Path to the recap JSON file (default: ./recap.json)")
    parser.add_argument("--output", default=None,
                        help="Output path (default: overwrites --recap file)")
    args = parser.parse_args()

    details_dir = Path(args.details_dir)
    recap_path = Path(args.recap)
    output_path = Path(args.output) if args.output else recap_path

    if not details_dir.is_dir():
        print(f"Error: details directory '{details_dir}' does not exist.")
        return
    if not recap_path.is_file():
        print(f"Error: recap file '{recap_path}' does not exist.")
        return

    print(f"Details dir : {details_dir}")
    print(f"Recap file  : {recap_path}")
    print(f"Output file : {output_path}\n")

    sync(details_dir, recap_path, output_path)


if __name__ == "__main__":
    main()