#!/usr/bin/env python3
"""
Group book JSON files by field values.

- List fields (e.g. subjects):  grouped by item count  (0, 1, 2, …)
- Scalar fields (e.g. description): grouped by present/non-empty (1) vs missing/empty (0)

When --show is used:
- ISBN is always included at the start of each book line
- Books are only listed for groups where at least one --fields value is missing/empty

Usage:
    python group_books_by_subjects.py <directory> [--fields FIELD ...] [--show FIELD ...]

Examples:
    # Default: group by 'subjects' count
    python group_books_by_subjects.py ./books

    # Group by presence of a scalar field
    python group_books_by_subjects.py ./books --fields description

    # Mix list and scalar fields (composite key)
    python group_books_by_subjects.py ./books --fields subjects description

    # Show extra fields for books with missing values only
    python group_books_by_subjects.py ./books --fields description cover --show title author
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_FIELDS = ["subjects"]


def load_book(filepath: Path) -> dict | None:
    """Load and parse a single book JSON file. Returns None on error."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [warning] Skipping {filepath.name}: {e}", file=sys.stderr)
        return None


def field_score(value) -> int:
    """
    Return a numeric score for a field value used as a group key:
    - list   → number of items (0, 1, 2, …)
    - scalar → 1 if present and non-empty, 0 if missing / None / empty string
    """
    if isinstance(value, list):
        return len(value)
    if value is None:
        return 0
    return 0 if str(value).strip() == "" else 1


def is_list_field(books: list[dict], field: str) -> bool:
    """Detect whether a field is a list by inspecting the loaded books."""
    for book in books:
        value = book.get(field)
        if value is not None:
            return isinstance(value, list)
    return False


def key_has_missing(key: tuple, fields: list[str], all_books: list[dict]) -> bool:
    """Return True if any scalar field in this key is missing (score=0)."""
    for field, score in zip(fields, key):
        if not is_list_field(all_books, field) and score == 0:
            return True
    return False


def make_group_key(book: dict, fields: list[str]) -> tuple[int, ...]:
    """Return a tuple of scores for each requested field."""
    return tuple(field_score(book.get(field)) for field in fields)


def group_books(directory: Path, fields: list[str]) -> dict[tuple, list[dict]]:
    """Walk a directory and group books by the composite key of the given fields."""
    json_files = sorted(directory.glob("*.json"))

    if not json_files:
        print(f"No .json files found in '{directory}'.", file=sys.stderr)
        sys.exit(1)

    groups: dict[tuple, list[dict]] = defaultdict(list)

    for filepath in json_files:
        book = load_book(filepath)
        if book is None:
            continue
        key = make_group_key(book, fields)
        groups[key].append(book)

    return groups


def format_book_line(book: dict, show_fields: list[str]) -> str:
    """Return an indented line with ISBN always first, then the requested fields."""
    isbn = book.get("isbn", "N/A")
    parts = [f"isbn: {isbn}"]
    for field in show_fields:
        if field == "isbn":
            continue  # already added
        value = book.get(field, "N/A")
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value) if value else "—"
        parts.append(f"{field}: {value}")
    return "    - " + "  |  ".join(parts)


def format_key_label(key: tuple, fields: list[str], all_books: list[dict]) -> str:
    """
    Human-readable group header.
    List fields show the count; scalar fields show 'present' / 'missing'.
    """
    parts = []
    for field, score in zip(fields, key):
        if is_list_field(all_books, field):
            parts.append(f"{field}={score}")
        else:
            parts.append(f"{field}={'present' if score else 'missing'}")
    return ", ".join(parts)


def print_report(
        groups: dict[tuple, list[dict]],
        fields: list[str],
        show_fields: list[str] | None,
) -> None:
    """Print a summary report sorted by the composite key."""
    all_books = [b for books in groups.values() for b in books]
    total_books = len(all_books)
    field_str = ", ".join(f"'{f}'" for f in fields)

    print(f"\n{'='*60}")
    print(f"  BOOKS GROUPED BY: {field_str}")
    print(f"  Total: {total_books} book(s) across {len(groups)} group(s)")
    print(f"{'='*60}\n")

    for key in sorted(groups.keys()):
        books = groups[key]
        label = format_key_label(key, fields, all_books)
        print(f"  [{label}]  —  {len(books)} book(s)")

        # Only list individual books (with ISBN) when at least one scalar field is missing
        if show_fields and key_has_missing(key, fields, all_books):
            for book in books:
                print(format_book_line(book, show_fields))

        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Group book JSON files by field values. "
            "List fields are grouped by item count; "
            "scalar fields by presence (1) or absence (0). "
            "With --show, ISBN is always included and books are only "
            "listed for groups where a field is missing."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Path to the directory containing book .json files",
    )
    parser.add_argument(
        "--fields",
        nargs="+",
        default=DEFAULT_FIELDS,
        metavar="FIELD",
        help=(
            "One or more fields to group by (default: subjects). "
            "List fields group by count; scalar fields group by present/missing. "
            "e.g. --fields subjects description cover"
        ),
    )
    parser.add_argument(
        "--show",
        nargs="+",
        default=None,
        metavar="FIELD",
        help=(
            "Extra fields to display per book (ISBN is always shown). "
            "Books are only listed for groups where a --fields value is missing. "
            "e.g. --show title author year"
        ),
    )

    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"Error: '{args.directory}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    groups = group_books(args.directory, args.fields)
    print_report(groups, args.fields, args.show)


if __name__ == "__main__":
    main()