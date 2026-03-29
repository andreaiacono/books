#!/usr/bin/env python3
"""
Normalize publisher names in books.json using a hardcoded mapping.
Writes the result to a new file (default: books_harmonized.json).

Usage:
    python harmonize_publishers.py [--books PATH] [--out PATH] [--dry-run]

Options:
    --books     Path to input books.json  (default: data/books.json)
    --out       Path to output file       (default: data/books_harmonized.json)
    --dry-run   Print changes without writing
"""

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Mapping: raw value → canonical name
# Add or edit entries here. Keys are matched case-insensitively and after
# stripping leading/trailing whitespace.
# ---------------------------------------------------------------------------
PUBLISHER_MAP: dict[str, str] = {

    # ── Adelphi ──────────────────────────────────────────────────────────────
    "Adelphi Edizioni spa":             "Adelphi",

    # ── Addison-Wesley ───────────────────────────────────────────────────────
    "Addison Wesley":                   "Addison-Wesley Professional",
    "Addison Wesley Professional":      "Addison-Wesley Professional",

    # ── Bloomsbury ───────────────────────────────────────────────────────────
    "Bloomsbury Paperbacks":            "Bloomsbury Publishing",
    "Bloomsbury Publishing Plc":        "Bloomsbury Publishing",

    # ── Bompiani ─────────────────────────────────────────────────────────────
    "BOMPIANI":                         "Bompiani",
    "Tascabili Bompiani":               "Bompiani",          # or keep separate?

    # ── BUR / Rizzoli ────────────────────────────────────────────────────────
    "Bur":                              "Rizzoli",
    "Bureau Biblioteca Univ. Rizzoli":  "Rizzoli",
    "BUR Biblioteca Univ. Rizzoli":     "Rizzoli",
    "RIZZOLI":                          "Rizzoli",

    # ── CONFLUENCIAS ─────────────────────────────────────────────────────────
    "Codice Edizioni":                  "Codice",

    # ── CONFLUENCIAS ─────────────────────────────────────────────────────────
    "CONFLUENCIAS":                     "Confluencias",

    # ── Donzelli ─────────────────────────────────────────────────────────────
    "Donzelli Editore":                 "Donzelli",

    # ── E/O ──────────────────────────────────────────────────────────────────
    "Edizioni e/ o":                    "E/O",

    # ── EDT ──────────────────────────────────────────────────────────────────
    "EDT srl":                          "EDT",

    # ── Einaudi ──────────────────────────────────────────────────────────────
    "Giulio Einaudi Editore":           "Einaudi",
    "Einaudi Ragazzi":                  "Einaudi",

    # ── Elèuthera ────────────────────────────────────────────────────────────
    # One entry has a different encoding of the accented character
    "Elèuthera":                       "Elèuthera",

    # ── Faber & Faber ────────────────────────────────────────────────────────
    "Faber and Faber":                  "Faber & Faber",
    "FABER AND FABER":                  "Faber & Faber",
    "Faber And Faber Ltd.":             "Faber & Faber",
    "Faber Faber Inc":                  "Faber & Faber",
    "Guardian Faber Publishing":        "Faber & Faber",     # imprint of F&F — review?

    # ── Fazi ─────────────────────────────────────────────────────────────────
    "Fazi Editore":                     "Fazi",
    "Fazi editore":                     "Fazi",

    # ── FELTRINELLI ──────────────────────────────────────────────────────────
    "FELTRINELLI":                      "Feltrinelli",
    "Feltrinelli Editore":              "Feltrinelli",
    "Gramma Feltrinelli":               "Feltrinelli",       # review: might be a distinct imprint

    # ── Frilli ───────────────────────────────────────────────────────────────
    "F.lli Frilli":                     "Frilli",

    # ── Garzanti ─────────────────────────────────────────────────────────────
    "Garzanti Linguistica":             "Garzanti",    # review: keep separate?
    "Garzanti Libri":                   "Garzanti",    # review: keep separate?

    # ── Giunti ───────────────────────────────────────────────────────────────
    "Giunti":                           "Giunti Editore",
    "GIUNTI EDITORE":                   "Giunti Editore",

    # ── Granta ──────────────────────────────────────────────────────────────
    "Granta Publications":              "Granta Books",

    # ── HarperCollins ────────────────────────────────────────────────────────
    "HarperCollins Publishers":         "HarperCollins",
    "Collins":                          "HarperCollins",
    "HarperCollins Publishers Limited": "HarperCollins",
    "HarperCollins UK":                 "HarperCollins",
    "HarperCollins Italia":             "HarperCollins",
    "Harper":                           "HarperCollins",     # review: could be standalone

    # ── Hodder & Stoughton ───────────────────────────────────────────────────
    "Hodder And Stoughton Ltd.":        "Hodder & Stoughton",
    "Hodder Paperback":                 "Hodder & Stoughton",

    # ── Hoepli ───────────────────────────────────────────────────────────────
    "HOEPLI EDITORE":                   "Hoepli",

    # ── Il Mulino ────────────────────────────────────────────────────────────
    "Il mulino":                        "Il Mulino",


    # ── Il Sole 24 Ore ────────────────────────────────────────────────────────────
    "24 Ore Cultura - Codice Edizioni": "Il Sole 24 Ore",
    "24 Ore Cultura":                   "Il Sole 24 Ore",


    # ── Incorporated / Limited / LLC ─────────────────────────────────────────
    # These look like truncated publisher names — mapped to a placeholder.
    # Review and replace with correct names if possible.
    "Incorporated":                     "UNKNOWN (was: Incorporated)",
    "Limited":                          "UNKNOWN (was: Limited)",
    "Inc.":                             "UNKNOWN (was: Inc.)",
    'Inc."':                            "UNKNOWN (was: Inc.\")",
    '"O\'Reilly Media':                 "O'Reilly",
    "O'Reilly Media":                   "O'Reilly",
    "LLC":                              "UNKNOWN (was: LLC)",
    "S. A.":                            "UNKNOWN (was: S. A.)",

    # ── Infinito ─────────────────────────────────────────────────────────────
    "Infinito edizioni":                "Infinito",

    # ── Jackson ──────────────────────────────────────────────────────────────
    "Jackson":                          "Jackson Libri",

    # ── La nave di Teseo ─────────────────────────────────────────────────────
    "La Nave di Teseo Editore spa":     "La nave di Teseo",

    # ── La Spiga ──────────────────────────────────────────────────────────────
    "Tascabili La spiga":     "La Spiga",
    "La Spiga-Meravigli":     "La Spiga",
    "La Spiga Languages":     "La Spiga",

    # ── Laterza ──────────────────────────────────────────────────────────────
    "Laterza Edizioni Scolastiche":     "Laterza",           # review: keep separate?

    # ── Liguori ──────────────────────────────────────────────────────────────
    "Liguori Editore Srl":              "Liguori",

    # ── Linea d'Ombra ────────────────────────────────────────────────────────
    "Linea D'Ombra":                    "Linea d'Ombra",

    # ── Manning ──────────────────────────────────────────────────────────────
    "Manning Publications Co. LLC":     "Manning Publications",
    "Manning Publications Company":     "Manning Publications",

    # ── Marsilio ─────────────────────────────────────────────────────────────
    "Marsilio Editori spa":             "Marsilio",

    # ── McGraw-Hill ──────────────────────────────────────────────────────────
    "McGrawHill Education":             "McGraw-Hill Education",

    # ── Meltemi ──────────────────────────────────────────────────────────────
    "Meltemi Editore srl":              "Meltemi",

    # ── Mondadori ────────────────────────────────────────────────────────────
    "A. Mondadori":                     "Mondadori",
    "Arnoldo Mondadori Editore":        "Mondadori",
    "Edizioni Mondadori":               "Mondadori",
    "Mondadori Bruno":                  "Bruno Mondadori",         # review: Bruno Mondadori is an educational imprint
    "Bruno Mondadori":                  "Bruno Mondadori",         # review: same as above
    "Scolastiche Bruno Mondadori":      "Bruno Mondadori",         # review: same
    "Mondadori Education":              "Mondadori",         # review: keep separate?
    "Mondadori Electa":                 "Mondadori",         # review: art/illustrated imprint
    "Mondadori Informatica":            "Mondadori",
    "Mondadori Urania":                 "Mondadori",         # review: SF imprint

    # ── Mursia ───────────────────────────────────────────────────────────────
    "Ugo Mursia Editore":               "Mursia",

    # ── Newton Compton ───────────────────────────────────────────────────────
    "Newton Compton Editori":           "Newton Compton",

    # ── Nord ───────────────────────────────────────────────────────
    "Nord":                             "Editrice Nord",

    # ── Pearson ──────────────────────────────────────────────────────────
    "Pearson Italia S.p.a.":            "Pearson",
    "Pearson Education":                "Pearson",

    # ── Penguin ──────────────────────────────────────────────────────────────
    "Allen Lane":                       "Penguin",           # Penguin imprint — review
    "Allan Lane":                       "Penguin",           # typo of Allen Lane
    "Penguin Books":                    "Penguin",
    "Penguin Books Limited":            "Penguin",
    "Penguin Classics":                 "Penguin",           # review: keep as imprint?
    "Penguin Group":                    "Penguin",
    "Penguin Publishing Group":         "Penguin",
    "Penguin Random House":             "Penguin",           # review: distinct group?
    "Penguin Random House South Africa":"Penguin",
    "Penguin UK":                       "Penguin",
    "Penguin Young Readers Group":      "Penguin",

    # ── Profile Books ────────────────────────────────────────────────────────
    "Profile Books(GB)":                "Profile Books",
    "Profile Books Limited":            "Profile Books",

    # ── Prospettiva ──────────────────────────────────────────────────────────
    "Prospettiva Editrice":             "Prospettiva",

    # ── Raffaello Cortina ────────────────────────────────────────────────────
    "Raffaello Cortina Editore":        "Raffaello Cortina",
    "Raffaello Cortina editore":        "Raffaello Cortina",
    "Cortina Raffaello":                "Raffaello Cortina",

    # ── Random House ─────────────────────────────────────────────────────────
    "Random House Audio Publishing Group": "Random House",
    "Random House Publishing Group":    "Random House",

    # ── Sellerio ─────────────────────────────────────────────────────────────
    "Sellerio Editore Palermo":         "Sellerio",          # review: keep the full name?
    "Sellerio":                         "Sellerio",

    # ── Sellerio ─────────────────────────────────────────────────────────────
    "Simon & Schuster (UK)":           "Simon & Schuster",
    "Avid Reader Press / Simon & Schuster":  "Simon & Schuster",

    # ── Stampa Alternativa ───────────────────────────────────────────────────
    "Stampa alternativa/Nuovi equilibri": "Stampa Alternativa",

    # ── Thames & Hudson ──────────────────────────────────────────────────────
    "thames & hudson uk":               "Thames & Hudson",

    # ── Utet ─────────────────────────────────────────────────────────────────
    "Utet Libri":                       "UTET",

    # ── Vallardi ─────────────────────────────────────────────────────────────
    "Vallardi A.":                      "Vallardi",
    "Vallardi Industrie Grafiche":      "Vallardi",
    "Vallardi Viaggi":                  "Vallardi",          # review: travel imprint?

    # ── Vintage ──────────────────────────────────────────────────────────────
    "Vintage Books":                    "Vintage",
    "Vintage Classic":                  "Vintage",

    # ── White Star ───────────────────────────────────────────────────────────
    "EDIZIONI WHITE STAR  SRL":         "White Star",

    # ── © Editrice il Sirente ────────────────────────────────────────────────
    "© Editrice il Sirente":            "Editrice il Sirente",

}
# ---------------------------------------------------------------------------


def serialize_books(books: list[dict]) -> str:
    """
    Serialize books to match the books.json format:
    - Array items each on their own line, no indentation
    - Sorted by 'added' ascending (missing 'added' sorts last)
    - 'description' key moved to the end of each object
    """
    def sort_key(book: dict) -> str:
        return book.get("added") or "9999-99-99"

    def reorder(book: dict) -> dict:
        description = book.pop("description", None)
        if description is not None:
            book["description"] = description
        return book

    sorted_books = [reorder(dict(b)) for b in sorted(books, key=sort_key)]

    lines = [json.dumps(book, ensure_ascii=False, separators=(",", ":"))
             for book in sorted_books]
    return "[\n" + ",\n".join(lines) + "\n]"


def normalize(raw: str) -> str:
    """Return the canonical name for a publisher string, or the original if unmapped."""
    return PUBLISHER_MAP.get(raw.strip(), raw.strip())


def harmonize(books_path: Path, out_path: Path, dry_run: bool) -> None:
    with open(books_path, "r", encoding="utf-8") as f:
        books = json.load(f)

    changes: list[tuple[str, str, str]] = []  # (isbn, old, new)

    for book in books:
        raw = book.get("publisher")
        if not raw:
            continue
        canonical = normalize(raw)
        if canonical != raw:
            changes.append((book.get("isbn", "?"), raw, canonical))
            if not dry_run:
                book["publisher"] = canonical

    # ── Report ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  PUBLISHER HARMONIZATION {'(DRY RUN) ' if dry_run else ''}REPORT")
    print(f"  Input : {books_path}")
    if not dry_run:
        print(f"  Output: {out_path}")
    print(f"  Total changes: {len(changes)}")
    print(f"{'='*60}\n")

    if changes:
        col = max(len(old) for _, old, _ in changes)
        for isbn, old, new in sorted(changes, key=lambda x: x[1].lower()):
            print(f"  {old:<{col}}  →  {new}   (isbn: {isbn})")
    else:
        print("  No changes needed.")

    print()

    if not dry_run and changes:
        tmp = out_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(serialize_books(books))
        tmp.replace(out_path)
        print(f"  Saved {len(changes)} change(s) to {out_path}.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize publisher names in books.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--books", type=Path, default=Path("data/books.json"),
        help="Path to input books.json (default: data/books.json)",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Path to output file (default: <input-stem>_harmonized.json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print changes without writing any file",
    )
    args = parser.parse_args()

    if not args.books.is_file():
        print(f"Error: '{args.books}' not found.", file=sys.stderr)
        sys.exit(1)

    out = args.out or args.books.with_stem(args.books.stem + "_harmonized")
    harmonize(args.books, out, args.dry_run)


if __name__ == "__main__":
    main()