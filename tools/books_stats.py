#!/usr/bin/env python3
"""
Group books by field values from a single books.json file.

- List fields (e.g. subjects):  grouped by item count  (0, 1, 2, …)
- Scalar fields (e.g. description): grouped by present/non-empty (1) vs missing/empty (0)

When --show is used:
- ISBN is always included at the start of each book line
- Books are only listed for groups where at least one --fields value is missing/empty

Usage:
    python books_stats.py [--books PATH] [--fields FIELD ...] [--show FIELD ...]

Examples:
    # Default: group by 'subjects' count
    python books_stats.py

    # Group by presence of a scalar field
    python books_stats.py --fields description

    # Mix list and scalar fields (composite key)
    python books_stats.py --fields subjects description

    # Show extra fields for books with missing values only
    python books_stats.py --fields description cover --show title author
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_FIELDS = ["subjects"]


def load_books(filepath: Path) -> list[dict]:
    """Load books.json and return entries with real ISBNs."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            books = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: cannot read {filepath}: {e}", file=sys.stderr)
        sys.exit(1)
    return [b for b in books if not b.get("isbn", "").startswith("noisbn_")]


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


def group_books(books_path: Path, fields: list[str]) -> dict[tuple, list[dict]]:
    """Load books.json and group books by the composite key of the given fields."""
    all_books = load_books(books_path)

    if not all_books:
        print(f"No books found in '{books_path}'.", file=sys.stderr)
        sys.exit(1)

    groups: dict[tuple, list[dict]] = defaultdict(list)

    for book in all_books:
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

        # List individual books when:
        # - --show is used and at least one scalar field is missing, OR
        # - the group has fewer than 5 books (show ISBNs only)
        if show_fields and key_has_missing(key, fields, all_books):
            for book in books:
                print(format_book_line(book, show_fields))
        elif len(books) < 12:
            for book in books:
                print(f"    - {book.get('isbn', 'N/A')} - {book.get('title', 'N/A')}")

        print()


def run_values(books_path: Path, field: str, sort_by: str = "count") -> None:
    """List all distinct values for a field with their occurrence counts."""
    all_books = load_books(books_path)

    counts: dict[str, int] = defaultdict(int)
    missing = 0

    for book in all_books:
        value = book.get(field)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            missing += 1
        elif isinstance(value, list):
            if not value:
                missing += 1
            else:
                for item in value:
                    counts[str(item)] += 1
        else:
            for item in str(value).split(","):
                item = item.strip()
                if item:
                    counts[item] += 1

    if not counts and not missing:
        print(f"  Field '{field}' not found in any book.")
        return

    if sort_by == "alpha":
        sorted_values = sorted(counts.items(), key=lambda x: x[0].lower())
    else:
        sorted_values = sorted(counts.items(), key=lambda x: (-x[1], x[0].lower()))

    total_books = len(all_books)
    distinct = len(counts)

    print(f"\n{'='*60}")
    print(f"  DISTINCT VALUES FOR: '{field}'")
    print(f"  Total books: {total_books}  |  Distinct values: {distinct}")
    if missing:
        print(f"  Books with missing/empty '{field}': {missing}")
    print(f"{'='*60}\n")

    max_val_len = max((len(v) for v in counts), default=0)
    col_width = min(max(max_val_len, 20), 50)

    for value, count in sorted_values:
        bar = "█" * min(count, 40)
        print(f"  {value:<{col_width}}  {count:>4}  {bar}")

    print()


def run_prune(books_path: Path, field: str) -> None:
    """Interactively prune list fields with more than one entry."""
    with open(books_path, "r", encoding="utf-8") as f:
        all_books = json.load(f)

    targets = [
        b for b in all_books
        if not b.get("isbn", "").startswith("noisbn_")
           and isinstance(b.get(field), list)
           and len(b[field]) > 1
    ]

    if not targets:
        print(f"  No books with more than one '{field}' entry.")
        return

    print(f"\n  Found {len(targets)} book(s) with multiple '{field}' entries.")
    print("  For each book: enter a replacement value, press Enter to skip, Ctrl-C to stop.\n")

    changed = 0
    try:
        for i, book in enumerate(targets, 1):
            isbn = book.get("isbn", "?")
            title = book.get("title", "?")
            values = book[field]
            print(f"  [{i}/{len(targets)}] {title}  ({isbn})")
            print(f"    Current {field} ({len(values)}): {', '.join(str(v) for v in values)}")
            reply = input("    New value (blank=skip): ").strip()
            if reply:
                book[field] = [reply]
                changed += 1
                print(f"    → set to: [{reply}]")
            else:
                print("    → skipped")
            print()
    except (KeyboardInterrupt, EOFError):
        print("\n  Interrupted.")

    if changed:
        tmp = books_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(all_books, f, ensure_ascii=False, separators=(",", ":"))
        tmp.replace(books_path)
        print(f"  Saved {changed} change(s) to {books_path}.")
    else:
        print("  No changes made.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Group books from books.json by field values. "
            "List fields are grouped by item count; "
            "scalar fields by presence (1) or absence (0). "
            "With --show, ISBN is always included and books are only "
            "listed for groups where a field is missing."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--books",
        type=Path,
        default=Path("data/books.json"),
        help="Path to books.json (default: data/books.json)",
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
    parser.add_argument(
        "--prune",
        metavar="FIELD",
        default=None,
        help=(
            "Interactively prune a list field where cardinality > 1. "
            "For each book, shows current values and lets you type a single replacement. "
            "e.g. --prune subjects"
        ),
    )
    parser.add_argument(
        "--values",
        metavar="FIELD",
        default=None,
        help=(
            "List all distinct values for a field with occurrence counts. "
            "List fields (e.g. subjects) enumerate individual items; "
            "scalar fields (e.g. lang, publisher) enumerate unique strings. "
            "e.g. --values subjects"
        ),
    )
    parser.add_argument(
        "--sort",
        choices=["count", "alpha"],
        default="count",
        help=(
            "Sort order for --values output: "
            "'count' (most frequent first, default) or 'alpha' (alphabetical)."
        ),
    )

    args = parser.parse_args()

    if not args.books.is_file():
        print(f"Error: '{args.books}' not found.", file=sys.stderr)
        sys.exit(1)

    if args.prune:
        run_prune(args.books, args.prune)
        return

    if args.values:
        run_values(args.books, args.values, args.sort)
        return

    groups = group_books(args.books, args.fields)
    print_report(groups, args.fields, args.show)


if __name__ == "__main__":
    main()