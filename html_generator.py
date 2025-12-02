import csv
from datetime import datetime
from collections import defaultdict


def parse_date(date_str):
    """Parse date string in format DD/MM/YYYY"""
    return datetime.strptime(date_str, '%d/%m/%Y')


def generate_book_url(isbn):
    """Generate OpenLibrary URL from ISBN"""
    if isbn:
        return f"https://books.google.it/books?vid={isbn}"
    return None


def read_books(csv_file):
    """Read books from CSV and organize by year"""
    books_by_year = defaultdict(list)

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = parse_date(row['date'])
            year = date.year
            books_by_year[year].append({
                'date': date,
                'title': row['title'],
                'comment': row['comment'],
                'creators': row['creators'],
                'isbn': row['isbn']
            })

    # Sort books within each year by date
    for year in books_by_year:
        books_by_year[year].sort(key=lambda x: x['date'], reverse=True)

    return books_by_year


def generate_html(books_by_year, output_file):
    """Generate HTML page from books data"""

    # Calculate total books
    total_books = sum(len(books) for books in books_by_year.values())

    html = """<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reading List</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            color: #2c3e50;
        }

        .subtitle {
            color: #7f8c8d;
            margin-bottom: 40px;
            font-size: 1.1em;
        }

        .stats {
            background: #ecf0f1;
            padding: 20px;
            border-radius: 4px;
            margin-bottom: 40px;
            text-align: center;
        }

        .stats span {
            font-size: 2em;
            font-weight: bold;
            color: #3498db;
        }

        .year-section {
            margin-bottom: 50px;
        }

        .year-header {
            font-size: 1.8em;
            color: #2c3e50;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #3498db;
        }

        .book {
            margin-bottom: 1px;
            padding: 1px;
            transition: background-color 0.2s;
            border-radius: 4px;
        }

        .book:hover {
            background-color: #f8f9fa;
        }

        .book-date {
            color: #7f8c8d;
            font-size: 0.9em;
            display: inline-block;
            min-width: 80px;
        }

        .book-title {
            color: #2c3e50;
            text-decoration: none;
            font-weight: 500;
            transition: color 0.2s;
        }

        .book-title:hover {
            color: #3498db;
        }

        .book-title.no-link {
            color: #2c3e50;
            cursor: default;
        }

        .book-authors {
            color: #95a5a6;
            font-style: italic;
            margin-left: 10px;
        }

        .book-comment {
            color: #7f8c8d;
            font-size: 0.9em;
            margin-left: 0px;
        }

        @media (max-width: 768px) {
            .container {
                padding: 20px;
            }

            h1 {
                font-size: 2em;
            }

            .book-date {
                display: block;
                margin-bottom: 5px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Reading List</h1>
        <p class="subtitle">Books I've read over the years</p>

        <div class="stats">
            <span>""" + str(total_books) + """</span> books read
        </div>

        <div id="booksList">
"""

    # Sort years in descending order
    for year in sorted(books_by_year.keys(), reverse=True):
        html += f"""
            <div class="year-section">
                <h2 class="year-header">{year}</h2>
"""

        for book in books_by_year[year]:
            date_str = book['date'].strftime('%d/%m/%y')
            title = book['title']
            isbn = book['isbn']
            creators = book['creators']
            comment = book['comment']
            if comment and comment[0] == ":":
                comment = comment[1:]

            # Create book title link or plain text
            if isbn:
                title_html = f'<a href="{generate_book_url(isbn)}" class="book-title" target="_blank">{title}</a>'
            else:
                title_html = f'<span class="book-title no-link">{title}</span>'

            html += f"""
                <div class="book">
                    <span class="book-date">{date_str}</span>
                    {title_html}
"""

            if creators:
                html += f""" di {creators}
"""

            if comment:
                html += f"""
                    <span class="book-comment">{comment}</span>
"""

            html += """
                </div>
"""

        html += """
            </div>
"""

    html += """
        </div>
    </div>
</body>
</html>
"""

    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"HTML file generated: {output_file}")
    print(f"Total books: {total_books}")


if __name__ == "__main__":
    # Read the CSV file and generate HTML
    csv_file = "merged_books.csv"  # Change this to your CSV file path
    output_file = "books.html"  # Change this to your desired output file

    books_by_year = read_books(csv_file)
    generate_html(books_by_year, output_file)