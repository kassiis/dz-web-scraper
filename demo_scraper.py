"""
Quick demo showing both CLI and library usage of scraper.py powered by Scrapling.
"""

import http.server
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import threading
import time

DEMO_DIR = Path(__file__).parent.resolve()
SCRAPER_SCRIPT = str(DEMO_DIR / "scraper.py")
OUTPUT_JSON = str(DEMO_DIR / "demo_output.json")
sys.path.insert(0, str(DEMO_DIR))

DEMO_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Books & Tech Store</title>
    <meta name="description" content="A simple test store for scraping book data.">
    <meta property="og:title" content="Books & Tech Store">
</head>
<body>
    <h1>Featured Products</h1>
    <p>Welcome to our tech bookstore! Here are the latest books on programming and data science.</p>
    
    <div class="product">
        <h2 class="book-title">Python Crash Course</h2>
        <span class="price">$27.99</span>
        <p class="desc">A hands-on, project-based introduction to the Python programming language.</p>
    </div>
    
    <div class="product">
        <h2 class="book-title">Web Scraping with Scrapling</h2>
        <span class="price">$34.50</span>
        <p class="desc">Collecting data from the modern web using Scrapling and requests.</p>
    </div>

    <table class="summary-table">
        <tr><th>Category</th><th>Available Items</th></tr>
        <tr><td>Programming</td><td>15</td></tr>
        <tr><td>Data Science</td><td>8</td></tr>
    </table>

    <a href="/catalog">View Full Catalog</a>
    <img src="/img/books-banner.jpg" alt="Bookstore Banner">
</body>
</html>
"""


class DemoHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(DEMO_HTML.encode("utf-8"))


def main():
    # 1. Start temporary demo server
    server = socketserver.TCPServer(("127.0.0.1", 0), DemoHandler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)

    try:
        print("=== 1. Testing CLI Text Output ===")
        subprocess.run([sys.executable, SCRAPER_SCRIPT, url], check=True)

        print("\n=== 2. Testing CLI CSS Selector Extraction (.book-title, .price) ===")
        subprocess.run(
            [sys.executable, SCRAPER_SCRIPT, url, "-s", ".book-title, .price"],
            check=True,
        )

        print("\n=== 3. Testing CLI XPath Selector Extraction (//span[@class='price']) ===")
        subprocess.run(
            [sys.executable, SCRAPER_SCRIPT, url, "-s", "//span[@class='price']"],
            check=True,
        )

        print("\n=== 4. Testing CLI JSON Output File ===")
        subprocess.run(
            [sys.executable, SCRAPER_SCRIPT, url, "-f", "json", "-o", OUTPUT_JSON],
            check=True,
        )
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            print("Generated JSON preview (first 20 lines):")
            for line in f.readlines()[:20]:
                print("  " + line, end="")

        print("\n=== 5. Testing Python Library Import ===")
        from scraper import scrape_url

        data = scrape_url(url, selector=".book-title")
        print(f"Scraped Title: {data['metadata']['title']}")
        print(f"Found {len(data['tables'])} table(s)")
        print("CSS Selector matches:")
        for match in data["custom_selector"]["matches"]:
            print(f"  - {match['text']}")

    finally:
        server.shutdown()
        server.server_close()
        if os.path.exists(OUTPUT_JSON):
            os.remove(OUTPUT_JSON)

    print("\n[SUCCESS] All demonstrations executed successfully!")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
