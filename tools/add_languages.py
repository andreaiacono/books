#!/usr/bin/env python3
"""Add 'lang' field to books.json, inferred from title/description.

Renames 'language' → 'lang' and infers language for books missing it.
Heuristic: defaults to 'it' (Italian), switches to 'en'/'es'/'fr' based on
common title words/patterns.
"""

import json
import re
import sys

BOOKS_PATH = 'data/books.json'

# Common English words that rarely appear in Italian/Spanish/French titles
EN_WORDS = {
    # Excluded: a, in, no, or — overlap with Italian
    'the', 'of', 'and', 'to', 'an', 'for', 'on', 'with', 'from',
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'could', 'should', 'shall', 'may',
    'might', 'must', 'can', 'not', 'but', 'if', 'then', 'than',
    'so', 'as', 'at', 'by', 'up', 'out', 'off', 'into', 'over', 'after',
    'before', 'between', 'under', 'through', 'about', 'against', 'during',
    'without', 'within', 'along', 'following', 'across', 'behind', 'beyond',
    'this', 'that', 'these', 'those', 'it', 'its', 'his', 'her', 'their',
    'my', 'your', 'our', 'who', 'which', 'what', 'where', 'when', 'how',
    'why', 'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
    'some', 'such', 'only', 'own', 'same', 'new', 'old', 'long', 'great',
    'little', 'just', 'also', 'very', 'often', 'however', 'too', 'usually',
    'really', 'already', 'still', 'here', 'there', 'now', 'then',
    'man', 'men', 'woman', 'women', 'world', 'life', 'death', 'time',
    'book', 'story', 'stories', 'tale', 'tales', 'history',
    'dark', 'light', 'black', 'white', 'red', 'blue', 'green',
    'war', 'night', 'day', 'last', 'first', 'way', 'eye', 'eyes',
    'dream', 'dreams', 'fire', 'water', 'earth', 'wind', 'star', 'stars',
    'king', 'queen', 'lord', 'gods', 'god',
    'complete', 'guide', 'handbook', 'introduction', 'selected',
}

# Strong English markers — if title starts with these
EN_STARTERS = [
    'the ', 'an ',
    # 'a ' excluded — also Italian preposition
]

# Spanish markers
ES_WORDS = {
    # Excluded: del, al, en, con, entre, como, su, todo, toda, que, o —
    #           all overlap with Italian
    'el', 'los', 'las', 'por', 'para', 'sin',
    'sobre', 'hacia', 'desde', 'hasta', 'según', 'durante',
    'más', 'pero', 'sino', 'aunque', 'porque', 'donde', 'cuando',
    'quien', 'cual', 'qué', 'cómo', 'dónde', 'cuándo', 'quién',
    'sus', 'ese', 'esa', 'esos', 'esas', 'estos',
    'estas', 'aquel', 'aquella', 'otro', 'otra', 'otros', 'otras',
    'todos', 'todas', 'cada', 'mismo', 'misma',
    'mundo', 'vida', 'muerte', 'tiempo', 'hombre', 'mujer',
    'historia', 'ciudad', 'noche',
    'y', 'ni',
}

ES_STARTERS = [
    'el ', 'la ', 'los ', 'las ',
]

# French markers
FR_WORDS = {
    # Excluded: le, la, un, une, en, ou, et, que, qui, par, son, sa, mon, ma,
    #           ton, ta — all overlap with Italian
    'les', 'des', 'du', 'au', 'aux', 'dans', 'sur',
    'pour', 'avec', 'sans', 'sous', 'vers', 'chez',
    'mais', 'donc', 'car',
    'dont', 'où', 'quand', 'comment', 'pourquoi',
    'cette', 'ces', 'ses', 'mes', 'tes', 'leur', 'leurs', 'notre', 'votre',
    'homme', 'femme', 'monde', 'vie', 'mort', 'temps',
    'histoire', 'nuit', 'jour',
}

FR_STARTERS = [
    'les ',
    # 'le ', 'la ', "l'" excluded — also Italian articles
]

# Italian common words (to disambiguate from Spanish/French)
IT_WORDS = {
    'il', 'lo', 'la', 'gli', 'le', 'del', 'dello', 'della', 'dei', 'degli',
    'delle', 'al', 'allo', 'alla', 'ai', 'agli', 'alle', 'nel', 'nello',
    'nella', 'nei', 'negli', 'nelle', 'sul', 'sullo', 'sulla', 'sui',
    'sugli', 'sulle', 'dal', 'dallo', 'dalla', 'dai', 'dagli', 'dalle',
    'di', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra',
    'dell', 'nell', 'sull', 'dall', 'all',  # elided forms (l')
    'e', 'o', 'ma', 'che', 'non', 'se', 'come', 'più', 'anche', 'quando',
    'dove', 'perché', 'chi', 'cosa', 'quale', 'quanto',
    'un', 'uno', 'una', 'questo', 'questa', 'questi', 'queste',
    'quello', 'quella', 'quelli', 'quelle',
    'suo', 'sua', 'suoi', 'sue', 'mio', 'mia', 'miei', 'mie',
    'tuo', 'tua', 'tuoi', 'tue', 'nostro', 'nostra', 'nostri', 'nostre',
    'vostro', 'vostra', 'vostri', 'vostre', 'loro',
    'tutto', 'tutta', 'tutti', 'tutte', 'ogni', 'altro', 'altra',
    'mondo', 'vita', 'morte', 'tempo', 'uomo', 'donna', 'storia',
    'città', 'notte', 'giorno', 'anno', 'casa',
}

IT_STARTERS = [
    'il ', 'lo ', 'la ', 'gli ', 'i ',
    "l'", "un'", "un ", "una ",
]


def score_language(title, description=''):
    """Return (lang, confidence) for a book based on title + description."""
    text = title.lower()
    # Split on apostrophes too so "dell'ombra" → {"dell", "ombra"}
    words = set(re.findall(r"[a-zà-öø-ÿ]+", text))

    # Score each language by word overlap
    scores = {
        'it': len(words & IT_WORDS),
        'en': len(words & EN_WORDS),
        'es': len(words & ES_WORDS),
        'fr': len(words & FR_WORDS),
    }

    # Bonus for title starters
    for s in IT_STARTERS:
        if text.startswith(s):
            scores['it'] += 3
            break

    for s in EN_STARTERS:
        if text.startswith(s):
            scores['en'] += 3
            break

    for s in ES_STARTERS:
        if text.startswith(s):
            scores['es'] += 3
            break

    for s in FR_STARTERS:
        if text.startswith(s):
            scores['fr'] += 3
            break

    # Strong Italian-specific markers (articles that don't exist in other languages)
    for w in ['il', 'gli', 'dello', 'della', 'degli', 'delle', 'nella',
              'nelle', 'negli', 'nello', 'sullo', 'sulla', 'sugli', 'sulle',
              'dallo', 'dalla', 'dagli', 'dalle']:
        if w in words:
            scores['it'] += 2

    # Strong English markers
    for w in ['the', 'and', 'with', 'from', 'this', 'that', 'which', 'would',
              'could', 'should', 'have', 'been', 'being', 'their', 'about']:
        if w in words:
            scores['en'] += 2

    # Strong Spanish markers
    for w in ['los', 'las', 'por', 'para', 'pero', 'sino', 'aunque',
              'según', 'hacia', 'desde', 'hasta']:
        if w in words:
            scores['es'] += 2

    # Strong French markers
    for w in ['les', 'des', 'dans', 'pour', 'avec', 'sans', 'sous',
              'vers', 'chez', 'mais', 'donc', 'cette', 'dont']:
        if w in words:
            scores['fr'] += 2

    # If Italian words are present at all, default to Italian — Italian titles
    # commonly borrow English words, so mixed titles are almost always Italian
    if scores['it'] > 0:
        return 'it', scores['it']

    # No Italian signal: pick the highest-scoring language
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return 'it', 0  # no signal at all → default Italian
    return best, scores[best]


def main():
    dry_run = '--dry-run' in sys.argv

    with open(BOOKS_PATH, 'r', encoding='utf-8') as f:
        books = json.load(f)

    stats = {'kept': 0, 'inferred': 0, 'by_lang': {}}
    changes = []

    for book in books:
        # Rename language → lang
        old_lang = book.pop('language', '')

        if old_lang:
            book['lang'] = old_lang
            stats['kept'] += 1
        else:
            lang, confidence = score_language(
                book.get('title', ''),
                book.get('description', '')
            )
            book['lang'] = lang
            stats['inferred'] += 1
            if lang != 'it':
                changes.append((book['title'], lang, confidence))

        stats['by_lang'][book['lang']] = stats['by_lang'].get(book['lang'], 0) + 1

    print(f"Total books: {len(books)}")
    print(f"Kept existing: {stats['kept']}")
    print(f"Inferred: {stats['inferred']}")
    print(f"By language: {stats['by_lang']}")
    print(f"\nNon-Italian inferences ({len(changes)}):")
    for title, lang, conf in sorted(changes, key=lambda x: (-x[2], x[1])):
        print(f"  [{lang}] (conf={conf}) {title}")

    if not dry_run:
        # Write back
        json_str = '[\n' + ',\n'.join(json.dumps(b, ensure_ascii=False) for b in books) + '\n]\n'
        with open(BOOKS_PATH, 'w', encoding='utf-8') as f:
            f.write(json_str)
        print(f"\nWritten to {BOOKS_PATH}")
    else:
        print("\n(dry run — no changes written)")


if __name__ == '__main__':
    main()
