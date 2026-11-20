# Python Web Scraper (Powered by Scrapling)

A high-performance, robust, and extensible Python web scraper designed to extract small amounts of structured data from any given URL, powered by **Scrapling**.

## Features

- **Metadata Extraction**: Title, description, keywords, OpenGraph tags (`og:title`, `og:image`, etc.), and canonical URL.
- **Headings & Content**: Automatically collects `h1` through `h4` headings and cleans article/page paragraphs.
- **Links & Images**: Extracts all hyperlinks (resolved to absolute URLs and tagged as internal vs. external) and image sources with `alt` descriptions.
- **HTML Tables**: Parses tables into structured lists of Python dictionaries keyed by column headers.
- **Targeted CSS & XPath Selectors**: Extract specific elements on demand using either CSS selectors or XPath queries (e.g., `--selector ".price"` or `--selector "//span[@class='price']"`).
- **Algerian (.dz) DNS & Data Collection**:
  - Automatically verifies if a website has a `.dz` ccTLD or `.dz` DNS records (nameservers, mail servers, reverse DNS PTR).
  - Extracts Algerian telephone numbers (+213, 00213, 05/06/07 mobile, 02/03/04 landlines).
  - Detects all 58 Algerian wilayas (provinces).
  - Extracts commercial and administrative identifiers (NIF, NIS, RC, AI).
  - Collects discovered internal and external `.dz` hyperlinks.
  - `--dz-only` CLI flag to ensure the target has verified `.dz` domain or DNS before scraping.
- **Automatic Navigation (Crawler Mode)**:
  - Automatically crawls and navigates up to 10 related pages of the target URL (`--crawl`, `--max-pages 10`).
  - Stays within the domain, discovers internal paths, prevents cycles, and aggregates cross-page findings.
- **Google Information & Related URLs**:
  - Direct retrieval of Google search, site search, and cache URLs (`--google-info`).
  - Queries Google Suggest & Autocomplete for related search queries and direct navigation URLs.
  - Generates targeted Google section searches (about, contact, services, login).
- **Optional Stealth Fetching**: Built-in `--stealth` mode powered by Scrapling's `Fetcher` to evade basic anti-bot systems and TLS fingerprinting.
- **Multiple Output Formats**: Supports human-readable plain text, structured JSON, and clean Markdown.
- **Robust Network Handling**: Employs realistic browser `User-Agent` headers, timeout controls, and friendly error reporting.
- **Dual Usage**: Runs either directly from the terminal or as an importable Python library.

---

## Requirements & Installation

Requires Python 3.8+ with `scrapling` and `requests`:

```bash
pip install scrapling requests
```

---

## CLI Usage

### Basic Scraping (Prints to Console)
```bash
python scraper.py https://example.com
```

### Algerian (.dz) Website Scraping with Verification
```bash
python scraper.py algerietelecom.dz --dz-only
```

### Automatic Navigation Through 10 Related Pages
```bash
python scraper.py algerietelecom.dz --crawl --max-pages 10
```

### Retrieve Google Infos & Related URLs
```bash
python scraper.py algerietelecom.dz --google-info
```

### Save Crawl Output as JSON
```bash
python scraper.py algerietelecom.dz --crawl --max-pages 10 -f json -o output.json
```

### Save Output as Markdown
```bash
python scraper.py https://example.com -f markdown -o page.md
```

### Extract Specific Elements by CSS Selector
```bash
python scraper.py https://example.com --selector ".product-title, .price"
```

### Command Line Options

| Option | Flag | Description | Default |
|---|---|---|---|
| `url` | (Positional) | Target URL to scrape or crawl (e.g. `algerietelecom.dz`) | *Required* |
| `--crawl` | `-c` | Enable automatic navigation through related pages | `False` |
| `--max-pages` | `-m` | Maximum number of related pages to crawl | `10` |
| `--crawl-delay`| | Politeness delay in seconds between crawled pages | `0.5` |
| `--google-info`| `-g` | Fetch Google search information and related URLs | `False` |
| `--dz-only` | | Enforce that website has verified `.dz` domain or DNS | `False` |
| `--selector` | `-s` | CSS or XPath selector for specific elements | `None` |
| `--format` | `-f` | Output format (`text`, `json`, `markdown`) | `text` |
| `--output` | `-o` | Output file path | `None` (stdout) |
| `--timeout` | `-t` | HTTP request timeout in seconds | `15` |
| `--stealth` | | Use Scrapling stealth fetcher | `False` |
| `--no-verify-ssl` | | Disable SSL verification | `False` |

---

## Python Library Usage

You can import `scrape_url`, `crawl_website`, `fetch_google_info`, `get_dz_dns_info`, or `WebScraper` directly:

```python
from scraper import (
    WebScraper,
    scrape_url,
    crawl_website,
    fetch_google_info,
    get_dz_dns_info,
)

# 1. Quick scrape with Algerian .dz extraction & Google info
data = scrape_url("algerietelecom.dz", include_dz_data=True, include_google_info=True)
print("Title:", data["metadata"]["title"])
print("Algerian Phones:", data["dz_data"]["algerian_phones"])
print("Google Related URLs:", data["google_info"]["google_related_urls"])

# 2. Automatic navigation through 10 related pages
crawl_result = crawl_website("algerietelecom.dz", max_pages=10)
print(f"Crawled {crawl_result['total_pages_crawled']} pages:")
for page in crawl_result["pages"]:
    print(f"  #{page['page_number']}: {page['title']} -> {page['url']}")

# 3. Retrieve Google information and related URLs
g_info = fetch_google_info("elmoudjahid.dz")
print("Google Search URL:", g_info["google_search_url"])
print("Related Queries:", g_info["google_related_queries"])

# 4. Check .dz DNS info
dns_info = get_dz_dns_info("algerietelecom.dz")
print("Has .dz DNS:", dns_info["has_dz_dns"])
print("Nameservers:", dns_info["nameservers"])
```

---

## Running Tests

A comprehensive unit test suite is included in `test_scraper.py`:

```bash
python scraper/test_scraper.py
```
