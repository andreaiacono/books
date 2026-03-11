#!/usr/bin/env python3
"""
fetch_data.py — Fetch missing metadata and cover images for books in books.json.

Reads data/books.json, queries Google Books and Open Library APIs to fill in
missing fields (description, author, publisher, pages, subjects) and download
cover images.  Progress is tracked so interrupted runs can resume.

Usage:
  python3 fetch_data.py --check                          # audit, no API calls
  python3 fetch_data.py --metadata                       # fill missing fields
  python3 fetch_data.py --covers                         # download covers
  python3 fetch_data.py --metadata --covers              # both
  python3 fetch_data.py --interactive                    # manual cover URLs
  python3 fetch_data.py --covers --interactive           # auto then manual
  python3 fetch_data.py --metadata --fields description  # specific fields only
  python3 fetch_data.py --metadata --limit 20 --dry-run  # test run
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Error: 'requests' is required. Run: pip install requests")

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

SCRIPT_DIR = Path(__file__).parent
META_FIELDS = {"description", "author", "publisher", "pages", "subjects", "year"}
CHECK_FIELDS = META_FIELDS | {"cover"}
SAVE_EVERY = 20  # save books.json every N metadata updates


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_books(path, limit=None):
    with open(path, encoding="utf-8") as f:
        books = json.load(f)
    real = [b for b in books if not b["isbn"].startswith("noisbn_")]
    fake = len(books) - len(real)
    if fake:
        print(f"  Skipping {fake} entries with no ISBN.")
    subset = real[:limit] if limit else real
    return books, subset


def save_books(path, books):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def is_missing(book, field):
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


def missing_fields(book, target, force=False):
    if force:
        return set(target)
    return {f for f in target if is_missing(book, f)}


def iterate(items):
    return tqdm(items, unit="book") if tqdm else items


def log(msg):
    if not tqdm:
        print(msg)


# ─── Progress tracking ───────────────────────────────────────────────────────

def load_progress(path):
    if not path.exists():
        return {"meta": set(), "covers": set()}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {
            "meta":   set(data.get("completed_meta", [])),
            "covers": set(data.get("completed_covers", [])),
        }
    except Exception:
        print(f"  Warning: could not read {path}, starting fresh.", file=sys.stderr)
        return {"meta": set(), "covers": set()}


def save_progress(path, progress):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({
            "completed_meta":   sorted(progress["meta"]),
            "completed_covers": sorted(progress["covers"]),
        }, f, indent=2)
    tmp.replace(path)


# ─── API clients ─────────────────────────────────────────────────────────────

import re as _re
import html as _html


class GoogleQuotaExceeded(Exception):
    pass


_BROWSER_UA = (
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:147.0) Gecko/20100101 Firefox/147.0"
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def fetch_ibs(isbn, session):
    """Fetch metadata from IBS.it via JSON-LD structured data."""
    url = f"https://www.ibs.it/a/e/{isbn}"
    try:
        r = session.get(url, timeout=10, headers={"User-Agent": _BROWSER_UA})
        if r.status_code != 200:
            return {}
        page = r.text
    except Exception:
        return {}

    # Extract JSON-LD block
    m = _re.search(
        r'<script\s+type="application/ld\+json">(.*?)</script>',
        page, _re.DOTALL,
    )
    if not m:
        return {}

    try:
        ld = json.loads(m.group(1))
    except Exception:
        return {}

    # ld can be a single object or a list; Book data may be nested in mainEntity
    if isinstance(ld, list):
        ld = next((x for x in ld if "Book" in (x.get("@type") or [])), ld[0] if ld else {})
    if "mainEntity" in ld:
        ld = ld["mainEntity"]

    meta = {}
    if desc := (ld.get("description") or "").strip():
        if len(desc) > 40:
            meta["description"] = desc
    if pub := (ld.get("publisher") or "").strip():
        meta["publisher"] = pub
    if pages_str := ld.get("numberOfPages"):
        try:
            pages = int(pages_str)
            if pages > 0:
                meta["pages"] = pages
        except (ValueError, TypeError):
            pass
    if author := (ld.get("author") or "").strip():
        meta["author"] = author
    if date_pub := (ld.get("datePublished") or "").strip():
        m2 = _re.search(r"(\d{4})", date_pub)
        if m2:
            meta["year"] = int(m2.group(1))

    return meta


def fetch_google_books_web(isbn, session):
    """Scrape metadata from the Google Books website (no API key needed)."""
    url = f"https://books.google.com/books?vid={isbn}"
    try:
        r = session.get(url, timeout=10, headers={"User-Agent": _BROWSER_UA})
        if r.status_code != 200:
            return {}
        page = r.text
    except Exception:
        return {}

    meta = {}

    # Description from <meta name="description"> or <div id=synopsistext>
    m = _re.search(r'<meta\s+name="description"\s+content="([^"]+)"', page)
    if m:
        desc = _html.unescape(m.group(1)).strip()
        if len(desc) > 40:
            meta["description"] = desc

    # Bibliographic info table
    rows = _re.findall(
        r'<td class="metadata_label">.*?<span[^>]*>([^<]+)</span>.*?'
        r'<td class="metadata_value">.*?<span[^>]*>(.*?)</span>',
        page, _re.DOTALL,
    )
    for label, value in rows:
        label = _html.unescape(label).strip().lower()
        value = _re.sub(r"<[^>]+>", "", _html.unescape(value)).strip()
        if not value:
            continue
        if label in ("editore", "publisher", "éditeur", "verlag", "editorial"):
            # strip trailing year like "Publisher, 2007"
            pub = _re.sub(r",\s*\d{4}$", "", value).strip()
            if pub:
                meta["publisher"] = pub
        if label in ("lunghezza", "length", "longueur", "länge", "longitud",
                      "pages", "pagine"):
            m2 = _re.search(r"(\d+)", value)
            if m2:
                meta["pages"] = int(m2.group(1))
        if label in ("autore", "author", "auteur", "autor"):
            meta.setdefault("author", value)
        if label in ("data di pubblicazione", "published", "date de publication",
                      "veröffentlichungsdatum", "año de edición"):
            m2 = _re.search(r"(\d{4})", value)
            if m2:
                meta["year"] = int(m2.group(1))
        if label in ("categorie", "categories", "catégories", "kategorien"):
            subjects = [s.strip() for s in value.split(",") if s.strip()]
            if subjects:
                meta["subjects"] = subjects

    return meta


def fetch_google_books(isbn, session, api_key=None):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    if api_key:
        url += f"&key={api_key}"

    for attempt in range(5):
        try:
            r = session.get(url, timeout=10)
            if r.status_code == 429:
                if attempt < 4:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    print(f"\n  Rate-limited, retrying in {wait:.1f}s …", flush=True)
                    time.sleep(wait)
                    continue
                if api_key:
                    raise GoogleQuotaExceeded("HTTP 429 — API key quota exhausted.")
                return {}, None
            if r.status_code == 403:
                raise GoogleQuotaExceeded("HTTP 403 — check API key/permissions.")
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                err = data["error"]
                if err.get("code") in {429, 403} or "quota" in str(err).lower():
                    raise GoogleQuotaExceeded(err.get("message", str(err)))
        except GoogleQuotaExceeded:
            raise
        except Exception:
            return {}, None

        items = data.get("items", [])
        if not items:
            return {}, None

        item = items[0]
        info = item.get("volumeInfo", {})

        # The search endpoint often omits fields like description, publisher,
        # pageCount; the individual volume endpoint (selfLink) usually has them.
        missing_detail = (
            not info.get("description")
            or not info.get("publisher")
            or not info.get("pageCount")
        )
        if missing_detail and (self_link := item.get("selfLink")):
            vol_url = self_link
            if api_key:
                vol_url += f"?key={api_key}"
            for vol_attempt in range(3):
                try:
                    r2 = session.get(vol_url, timeout=10)
                    if r2.status_code == 429:
                        wait = (2 ** vol_attempt) + random.uniform(0, 1)
                        time.sleep(wait)
                        continue
                    if r2.status_code == 200:
                        vol_info = r2.json().get("volumeInfo", {})
                        for key in ("description", "publisher", "pageCount"):
                            if not info.get(key) and vol_info.get(key):
                                info[key] = vol_info[key]
                    break
                except Exception:
                    break

        meta = {}
        if desc := info.get("description", "").strip():
            meta["description"] = desc
        if authors := info.get("authors"):
            meta["author"] = ", ".join(authors)
        if pub := info.get("publisher", "").strip():
            meta["publisher"] = pub
        if (pages := info.get("pageCount")) and isinstance(pages, int) and pages > 0:
            meta["pages"] = pages
        if pub_date := info.get("publishedDate", ""):
            m2 = _re.search(r"(\d{4})", pub_date)
            if m2:
                meta["year"] = int(m2.group(1))
        if categories := info.get("categories"):
            subjects, seen = [], set()
            for cat in categories:
                for part in cat.split("/"):
                    part = part.strip()
                    if part and part.lower() not in seen:
                        subjects.append(part)
                        seen.add(part.lower())
            if subjects:
                meta["subjects"] = subjects

        thumb = None
        for key in ("extraLarge", "large", "medium", "thumbnail"):
            if img_url := info.get("imageLinks", {}).get(key):
                thumb = img_url.replace("http://", "https://").replace("&edge=curl", "")
                break

        return meta, thumb

    return {}, None


def fetch_open_library_meta(isbn, session):
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        entry = r.json().get(f"ISBN:{isbn}", {})
    except Exception:
        return {}
    if not entry:
        return {}

    meta = {}
    desc = entry.get("notes") or entry.get("description")
    if isinstance(desc, dict):
        desc = desc.get("value")
    if isinstance(desc, str) and desc.strip():
        meta["description"] = desc.strip()
    if authors := entry.get("authors"):
        names = [a["name"].strip() for a in authors if a.get("name")]
        if names:
            meta["author"] = ", ".join(names)
    if pubs := entry.get("publishers"):
        if name := pubs[0].get("name", "").strip():
            meta["publisher"] = name
    if (pages := entry.get("number_of_pages")) and isinstance(pages, int) and pages > 0:
        meta["pages"] = pages
    if pub_date := entry.get("publish_date", ""):
        m = _re.search(r"(\d{4})", pub_date)
        if m:
            meta["year"] = int(m.group(1))
    if raw_subj := entry.get("subjects"):
        subjects, seen = [], set()
        for s in raw_subj:
            name = s.get("name", "").strip() if isinstance(s, dict) else str(s).strip()
            if name and name.lower() not in seen:
                subjects.append(name)
                seen.add(name.lower())
        if subjects:
            meta["subjects"] = subjects
    return meta


def fetch_cover(isbn, session, google_thumb=None):
    """Try AbeBooks → Google thumbnail → Open Library. Returns bytes or None."""
    # AbeBooks
    try:
        r = session.get(f"https://pictures.abebooks.com/isbn/{isbn}.jpg", timeout=10)
        if r.status_code == 200 and len(r.content) > 1000:
            if r.headers.get("Content-Type", "").startswith("image/"):
                return r.content, "ABE"
    except Exception:
        pass

    # Google thumbnail
    if google_thumb:
        try:
            r = session.get(google_thumb, timeout=10)
            r.raise_for_status()
            if len(r.content) > 1000:
                return r.content, "GB"
        except Exception:
            pass

    # Open Library
    try:
        for size in ("L", "M"):
            r = session.get(f"https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg", timeout=10)
            if r.status_code == 200 and len(r.content) > 1000:
                if r.headers.get("Content-Type", "").startswith("image/jpeg"):
                    return r.content, "OL"
    except Exception:
        pass

    return None, None


def convert_to_webp(data, quality=82):
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(data)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality, method=6)
    return buf.getvalue()


# ─── Commands ─────────────────────────────────────────────────────────────────

def run_check(args):
    from datetime import datetime, timezone

    books_path = Path(args.books)
    if not books_path.exists():
        sys.exit(f"Error: {books_path} not found.")
    _, real_books = load_books(books_path, args.limit)

    print(f"  Checking {len(real_books)} books …\n")

    field_counts = {f: 0 for f in CHECK_FIELDS}
    issues_list = []
    isbns_missing_meta = []
    isbns_missing_covers = []

    for entry in iterate(real_books):
        isbn, title = entry["isbn"], entry.get("title", "")
        issues = {}

        missing = [f for f in META_FIELDS if is_missing(entry, f)]
        if missing:
            for f in missing:
                field_counts[f] += 1
            issues["missing_fields"] = sorted(missing)
            isbns_missing_meta.append(isbn)

        if not (args.covers_dir / f"{isbn}.webp").exists():
            field_counts["cover"] += 1
            issues["missing_cover"] = True
            isbns_missing_covers.append(isbn)

        if issues:
            issues_list.append({"isbn": isbn, "title": title, "issues": issues})

    total = len(real_books)
    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": total,
            "fully_complete": total - len(issues_list),
            "books_with_issues": len(issues_list),
            "missing_cover_file": field_counts["cover"],
        },
        "field_missing_counts": {f: field_counts[f] for f in sorted(CHECK_FIELDS)},
        "books": issues_list,
        "isbns_missing_metadata": sorted(set(isbns_missing_meta)),
        "isbns_missing_covers": sorted(set(isbns_missing_covers)),
    }

    with open(args.check_report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    s = report["summary"]
    print("-- Check complete -----------------------------------------------")
    print(f"  Total:          {s['total']}")
    print(f"  Complete:       {s['fully_complete']}")
    print(f"  With issues:    {s['books_with_issues']}")
    print(f"  Missing cover:  {s['missing_cover_file']}")
    print()
    print("  Missing fields:")
    for field in sorted(CHECK_FIELDS):
        count = field_counts[field]
        print(f"    {field:<14} {count:>4}  {'#' * min(count, 40)}")
    print(f"\n  Report: {args.check_report}\n")


def run_interactive_covers(missing, covers_dir, session):
    stats = {"saved": 0, "skipped": 0, "errors": 0}
    total = len(missing)
    print(f"\n-- Interactive cover input ({total} books) --------------------")
    print("  Paste a direct image URL and press Enter. Blank to skip. Ctrl-C to stop.\n")
    try:
        for i, book in enumerate(missing, 1):
            isbn, title = book["isbn"], book.get("title", book["isbn"])
            dest = covers_dir / f"{isbn}.webp"
            print(f"  [{i}/{total}] {title}  ({isbn})")
            try:
                url = input("    URL: ").strip()
            except EOFError:
                print("\n  (stdin closed)")
                break
            if not url:
                stats["skipped"] += 1
                continue
            try:
                r = session.get(url, timeout=15)
                r.raise_for_status()
                if len(r.content) < 1000:
                    print("    WARNING: too small, skipped.")
                    stats["errors"] += 1
                    continue
            except Exception as e:
                print(f"    WARNING: {e}")
                stats["errors"] += 1
                continue
            try:
                img = convert_to_webp(r.content)
            except Exception:
                img = r.content
            dest.write_bytes(img)
            print("    OK")
            stats["saved"] += 1
    except KeyboardInterrupt:
        print("\n  Interrupted.")
    print(f"\n  Saved: {stats['saved']}  Skipped: {stats['skipped']}  Errors: {stats['errors']}\n")


def run_fetch(args):
    books_path = Path(args.books)
    if not books_path.exists():
        sys.exit(f"Error: {books_path} not found.")

    all_books, real_books = load_books(books_path, args.limit)
    target_fields = {f.strip().lower() for f in args.fields.split(",")}

    if args.covers or args.interactive:
        args.covers_dir.mkdir(parents=True, exist_ok=True)

    # Progress
    if args.reset_progress or args.force:
        progress = {"meta": set(), "covers": set()}
    else:
        progress = load_progress(args.progress_file)
        done_m, done_c = len(progress["meta"]), len(progress["covers"])
        if done_m or done_c:
            print(f"  Resuming: {done_m} meta / {done_c} covers already done.")

    tasks = [t for t, on in [("metadata", args.metadata), ("covers", args.covers),
                              ("interactive", args.interactive)] if on]
    print(f"\n  Tasks: {' '.join(tasks)}")
    if args.metadata:
        print(f"  Fields: {', '.join(sorted(target_fields))}")
    if args.dry_run:
        print("  [dry-run]")
    print()

    session = requests.Session()
    session.headers["User-Agent"] = "Biblio/1.0 (personal library; fetch_data)"

    books_dirty = False
    dirty_count = 0
    fill_counts = {f: 0 for f in target_fields}
    overwrite_counts = {f: 0 for f in target_fields}
    meta_not_found = cover_ok = cover_missing = 0
    google_quota_hit = False
    missing_covers = []

    for book in iterate(real_books):
        isbn = book["isbn"]
        title = book.get("title", isbn)
        label = f"[{isbn}] {title[:50]}"

        need_meta = args.metadata and (args.force or isbn not in progress["meta"])
        need_cover = args.covers and (args.force or isbn not in progress["covers"])
        if not need_meta and not need_cover:
            continue

        # Check if metadata actually needs filling
        needed = set()
        if need_meta:
            needed = missing_fields(book, target_fields, force=args.force)
            if not needed:
                if not args.dry_run:
                    progress["meta"].add(isbn)
                need_meta = False

        # Fetch metadata: 1) IBS.it  2) Google Books web  3) Open Library  4) Google Books API
        google_thumb = None

        # Fill metadata
        if need_meta:
            log(f"  ── {label}  need: {', '.join(sorted(needed))}")

            # 1) IBS.it (JSON-LD)
            ibs_meta = fetch_ibs(isbn, session)
            time.sleep(args.delay)
            if ibs_meta:
                log(f"     IBS     → {', '.join(sorted(ibs_meta.keys()))}")
            else:
                log(f"     IBS     → (nothing)")
            still_missing = needed - set(ibs_meta.keys())

            # 2) Google Books website (scrape)
            web_meta = {}
            if still_missing:
                web_meta = fetch_google_books_web(isbn, session)
                time.sleep(args.delay)
                if web_meta:
                    log(f"     GB-web  → {', '.join(sorted(web_meta.keys()))}")
                else:
                    log(f"     GB-web  → (nothing)")
                still_missing -= set(web_meta.keys())

            # 3) Open Library
            ol_meta = {}
            if still_missing:
                ol_meta = fetch_open_library_meta(isbn, session)
                time.sleep(args.delay)
                if ol_meta:
                    log(f"     OL      → {', '.join(sorted(ol_meta.keys()))}")
                else:
                    log(f"     OL      → (nothing)")
                still_missing -= set(ol_meta.keys())

            # 4) Google Books API (last resort, also gets cover thumbnail)
            api_meta = {}
            if (still_missing or need_cover) and not google_quota_hit:
                try:
                    api_meta, google_thumb = fetch_google_books(isbn, session, args.api_key)
                    time.sleep(args.delay)
                    if api_meta:
                        log(f"     GB-API  → {', '.join(sorted(api_meta.keys()))}")
                    else:
                        log(f"     GB-API  → (nothing)")
                except GoogleQuotaExceeded as e:
                    google_quota_hit = True
                    print(f"\n  GOOGLE QUOTA EXHAUSTED: {e}")
                    print("  Continuing with web scraping + Open Library.\n")

            filled = {}
            for f in needed:
                if f in ibs_meta:
                    filled[f] = ("IBS", ibs_meta[f])
                elif f in web_meta:
                    filled[f] = ("GB-web", web_meta[f])
                elif f in ol_meta:
                    filled[f] = ("OL", ol_meta[f])
                elif f in api_meta:
                    filled[f] = ("GB-API", api_meta[f])

            if filled:
                parts = [f"{f}[{src}]" for f, (src, _) in sorted(filled.items())]
                log(f"     FILLED  → {', '.join(parts)}")
                for f, (src, val) in filled.items():
                    if args.force and not is_missing(book, f):
                        overwrite_counts[f] += 1
                    else:
                        fill_counts[f] += 1
                if not args.dry_run:
                    book.update({f: val for f, (src, val) in filled.items()})
                    books_dirty = True
                    dirty_count += 1
                    if dirty_count % SAVE_EVERY == 0:
                        save_books(books_path, all_books)
            else:
                meta_not_found += 1
                log(f"     NOT FOUND (wanted: {', '.join(sorted(needed))})")

            if not args.dry_run:
                progress["meta"].add(isbn)
                save_progress(args.progress_file, progress)

        # Fetch cover
        if need_cover:
            # If we didn't go through the meta path, get google_thumb for covers
            if not need_meta and not google_quota_hit:
                try:
                    _, google_thumb = fetch_google_books(isbn, session, args.api_key)
                    time.sleep(args.delay)
                except GoogleQuotaExceeded as e:
                    google_quota_hit = True

            dest = args.covers_dir / f"{isbn}.webp"
            if dest.exists() and not args.force:
                if not args.dry_run:
                    progress["covers"].add(isbn)
                    save_progress(args.progress_file, progress)
                continue

            cover_bytes, cover_src = fetch_cover(isbn, session, google_thumb)
            time.sleep(args.delay)

            if cover_bytes:
                cover_ok += 1
                if args.convert:
                    try:
                        cover_bytes = convert_to_webp(cover_bytes)
                    except Exception:
                        pass
                if not args.dry_run:
                    dest.write_bytes(cover_bytes)
                log(f"  COVER OK [{cover_src}]  {label}")
            else:
                cover_missing += 1
                missing_covers.append({"isbn": isbn, "title": title})
                log(f"  COVER MISSING   {label}")

            if not args.dry_run:
                progress["covers"].add(isbn)
                save_progress(args.progress_file, progress)

    # Final save
    if books_dirty and not args.dry_run:
        save_books(books_path, all_books)
        print(f"  books.json updated ({dirty_count} entries changed).")

    # Summary
    print("\n-- Done ---------------------------------------------------------")
    if args.metadata:
        print("  Metadata:")
        for f in sorted(fill_counts):
            line = f"    {f:<14} filled: {fill_counts[f]}"
            if args.force and overwrite_counts[f]:
                line += f"  (overwritten: {overwrite_counts[f]})"
            print(line)
        print(f"    {'not found':<14}        {meta_not_found}")

    if args.covers:
        print(f"  Covers:  found: {cover_ok}  not found: {cover_missing}")
        if missing_covers and not args.dry_run:
            missing_path = args.covers_dir / "missing_covers.json"
            with open(missing_path, "w", encoding="utf-8") as f:
                json.dump(missing_covers, f, ensure_ascii=False, indent=2)
            print(f"    Missing ISBNs saved to: {missing_path}")

    # Interactive covers at the end
    if args.interactive and not args.dry_run:
        if not args.covers:
            missing_covers = [
                {"isbn": b["isbn"], "title": b.get("title", b["isbn"])}
                for b in real_books
                if not (args.covers_dir / f"{b['isbn']}.webp").exists()
            ]
        if missing_covers:
            run_interactive_covers(missing_covers, args.covers_dir, session)
        else:
            print("  No missing covers.")
    elif args.interactive and args.dry_run:
        print("  [dry-run] interactive skipped.")

    if google_quota_hit:
        print(f"\n  WARNING: Google quota exhausted. Progress saved to {args.progress_file}")
    if args.dry_run:
        print("  [dry-run] no files were written")
    print()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Fetch book metadata and/or cover images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--metadata",    action="store_true", help="Fill missing metadata fields")
    p.add_argument("--covers",      action="store_true", help="Download cover images")
    p.add_argument("--check",       action="store_true", help="Audit books, write report (no API calls)")
    p.add_argument("--interactive", action="store_true", help="Prompt for manual cover URLs")
    p.add_argument("--books",       default="data/books.json", help="Path to books.json")
    p.add_argument("--covers-dir",  type=Path, default=Path("covers"))
    p.add_argument("--fields",      default=",".join(sorted(META_FIELDS)))
    p.add_argument("--force",       action="store_true")
    p.add_argument("--dry-run",     action="store_true")
    p.add_argument("--convert",     action="store_true", help="Convert covers to WebP (needs Pillow)")
    p.add_argument("--api-key",     default=None, help="Google Books API key")
    p.add_argument("--progress-file", type=Path, default=SCRIPT_DIR / "fetch_progress.json")
    p.add_argument("--check-report",  type=Path, default=SCRIPT_DIR / "check_report.json")
    p.add_argument("--reset-progress", action="store_true")
    p.add_argument("--delay",       type=float, default=1.0, help="Seconds between API calls")
    p.add_argument("--limit",       type=int,   default=None, help="Process only first N books")

    args = p.parse_args()

    if not (args.metadata or args.covers or args.check or args.interactive):
        p.error("At least one of --metadata, --covers, --check, or --interactive is required.")

    # Validate fields
    requested = {f.strip().lower() for f in args.fields.split(",")}
    invalid = requested - META_FIELDS
    if invalid:
        p.error(f"Unknown field(s): {', '.join(sorted(invalid))}")

    if args.check:
        run_check(args)
        if not (args.metadata or args.covers or args.interactive):
            return

    # Interactive-only fast path (no API calls needed)
    if args.interactive and not args.covers and not args.metadata:
        session = requests.Session()
        session.headers["User-Agent"] = "Biblio/1.0"
        args.covers_dir.mkdir(parents=True, exist_ok=True)
        books_path = Path(args.books)
        if not books_path.exists():
            sys.exit(f"Error: {books_path} not found.")
        _, real_books = load_books(books_path, args.limit)
        missing = [
            {"isbn": b["isbn"], "title": b.get("title", b["isbn"])}
            for b in real_books
            if not (args.covers_dir / f"{b['isbn']}.webp").exists()
        ]
        if missing:
            run_interactive_covers(missing, args.covers_dir, session)
        else:
            print("  No missing covers.")
        return

    run_fetch(args)


if __name__ == "__main__":
    main()
