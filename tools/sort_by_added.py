#!/usr/bin/env python3
"""Sort data/books.json by 'added' date ascending."""

import json
from pathlib import Path

BOOKS = Path(__file__).resolve().parent.parent / "data" / "books.json"

books = json.loads(BOOKS.read_text(encoding="utf-8"))
books.sort(key=lambda b: b.get("added") or b.get("addedAt") or "0000-00-00")

def ordered(b):
    """Return book dict with description last."""
    desc = b.pop("description", None)
    out = dict(b)
    if desc is not None:
        out["description"] = desc
    return out

BOOKS.write_text(
    "[\n" + ",\n".join(json.dumps(ordered(b), ensure_ascii=False, separators=(",", ":")) for b in books) + "\n]\n",
    encoding="utf-8",
)

print(f"Sorted {len(books)} books by added date (asc).")
