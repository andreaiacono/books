import csv
import unicodedata
import re

ARTICLES = {
    "il", "lo", "la", "l", "i", "gli", "le",
    "un", "uno", "una", "dei", "degli", "delle",
}

def normalize_books_title(s):
    """Books file: convert vowel+' → vowel, remove punctuation."""
    s = re.sub(r"([aeiouAEIOU])'", r"\1", s)  # remove apostrophe after vowels

    s = s.lower()
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_isbn_title(s):
    """ISBN file: remove accents completely, remove punctuation."""
    s = ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )
    s = s.lower()
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# --- Load ISBN entries ---
isbn_entries = []
with open("isbns.txt", encoding="utf-8") as f:
    r = csv.DictReader(f, delimiter="\t")
    for row in r:
        orig = row["title"]
        isbn_entries.append((
            orig,
            normalize_isbn_title(orig),
            row.get("creators", ""),
            row.get("ean_isbn13", "")
        ))


# --- Helper: Matching function ---
def match_title(norm_book):
    """Try to match normalized book title against ISBN entries."""
    # 1. exact match
    for orig, norm, creators, isbn in isbn_entries:
        if norm == norm_book:
            return (orig, creators, isbn)

    # 2. substring match
    candidates = []
    for orig, norm, creators, isbn in isbn_entries:
        if norm_book in norm:
            candidates.append((len(norm), orig, creators, isbn))

    if candidates:
        # pick longest ISBN title (more precise)
        _, orig, creators, isbn = max(candidates)
        return (orig, creators, isbn)

    print("Unmatched: ", norm_book)
    return None


# --- Process books.txt ---
output = []
with open("books.txt", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        m = re.match(r"(\d{2}/\d{2}/\d{4})\s*-\s*\"(.+?)\"\s*,?(.*)", line)
        if not m:
            continue

        date, title, comment = m.groups()
        comment = comment.strip()

        norm_book = normalize_books_title(title)

        # --- First attempt ---
        result = match_title(norm_book)

        # --- If no match: remove article and retry ---
        if result is None:
            parts = norm_book.split()
            if parts and parts[0] in ARTICLES:
                norm_no_article = " ".join(parts[1:])
                if norm_no_article:
                    result = match_title(norm_no_article)

        if result is None:
            result = ("", "", "")

        output.append([
            date, title, comment,
            result[1], result[2]
        ])


# --- Write output ---
with open("merged_books.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "title", "comment", "isbn_title", "creators", "isbn"])
    w.writerows(output)

print("Done. Output written to merged_books.csv")
