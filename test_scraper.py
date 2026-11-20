"""
Unit and integration tests for scraper.py
"""

import http.server
import json
import os
import socketserver
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper import (
    WebScraper,
    crawl_website,
    extract_dz_data,
    fetch_google_info,
    format_as_markdown,
    format_as_text,
    get_dz_dns_info,
    get_google_info,
    is_dz_domain,
    scrape_url,
)

SAMPLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Sample Test Article</title>
    <meta name="description" content="This is a sample test meta description.">
    <meta name="keywords" content="python, web scraping, beautifulsoup">
    <link rel="canonical" href="https://test.local/canonical-article">
    <meta property="og:title" content="OpenGraph Article Title">
    <meta property="og:description" content="OpenGraph description content.">
    <meta property="og:image" content="https://test.local/og-image.jpg">
</head>
<body>
    <header>
        <h1>Main Article Headline</h1>
    </header>
    <main>
        <h2>Subheading Section 1</h2>
        <p>This is the first long paragraph with enough characters to be extracted properly.</p>
        <p>Here is another detailed paragraph discussing python web scraping techniques.</p>
        
        <h2>Subheading Section 2</h2>
        <div class="product-card" id="card-1">
            <span class="price">$19.99</span>
            <span class="item-name">Python Handbook</span>
        </div>
        <div class="product-card" id="card-2">
            <span class="price">$29.99</span>
            <span class="item-name">Advanced Scraping</span>
        </div>

        <table id="stats-table">
            <thead>
                <tr>
                    <th>Item</th>
                    <th>Qty</th>
                    <th>Price</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Widget A</td>
                    <td>10</td>
                    <td>$5.00</td>
                </tr>
                <tr>
                    <td>Widget B</td>
                    <td>25</td>
                    <td>$12.50</td>
                </tr>
            </tbody>
        </table>

        <a href="/about-us">About Us Page</a>
        <a href="https://external.org/docs">External Documentation</a>

        <img src="/images/diagram.png" alt="Architecture Diagram">
        <img src="https://test.local/images/photo.jpg" alt="Team Photo">
    </main>
</body>
</html>
"""


class MockHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """Simple HTTP server returning mock HTML for testing."""

    def log_message(self, format, *args):
        # Suppress server logs during test runs
        pass

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(SAMPLE_HTML.encode("utf-8"))
        elif self.path == "/404":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
        elif self.path.startswith("/nav/"):
            try:
                page_idx = int(self.path.split("/")[-1])
            except ValueError:
                page_idx = 0
            next1 = f"/nav/{page_idx + 1}"
            next2 = f"/nav/{page_idx + 2}"
            html = f"""<!DOCTYPE html>
            <html>
            <head><title>Related Page {page_idx}</title></head>
            <body>
                <h1>Page Heading {page_idx}</h1>
                <p>Detailed paragraph content for automatically navigated page {page_idx}.</p>
                <a href="{next1}">Go to page {page_idx + 1}</a>
                <a href="{next2}">Go to page {page_idx + 2}</a>
                <a href="https://other-domain.org/ext">External link</a>
                <p>Contact: +213 21 23 45 67 in Alger, NIF: 099812345678901</p>
            </body>
            </html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>OK</h1></body></html>")



class TestScraper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start a local HTTP server on a random port for live testing
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), MockHTTPHandler)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.scraper = WebScraper(timeout=5)

    def test_normalize_url(self):
        self.assertEqual(
            self.scraper.normalize_url("example.com"),
            "https://example.com",
        )
        self.assertEqual(
            self.scraper.normalize_url("http://example.com"),
            "http://example.com",
        )
        self.assertEqual(
            self.scraper.normalize_url("https://example.com"),
            "https://example.com",
        )

    def test_extract_metadata(self):
        data = self.scraper.scrape("https://test.local", html_content=SAMPLE_HTML)
        meta = data["metadata"]
        self.assertEqual(meta["title"], "Sample Test Article")
        self.assertEqual(meta["description"], "This is a sample test meta description.")
        self.assertEqual(meta["keywords"], "python, web scraping, beautifulsoup")
        self.assertEqual(meta["canonical_url"], "https://test.local/canonical-article")
        self.assertIn("open_graph", meta)
        self.assertEqual(meta["open_graph"]["og:title"], "OpenGraph Article Title")

    def test_extract_headings(self):
        data = self.scraper.scrape("https://test.local", html_content=SAMPLE_HTML)
        headings = data["headings"]
        self.assertIn("h1", headings)
        self.assertEqual(headings["h1"], ["Main Article Headline"])
        self.assertIn("h2", headings)
        self.assertEqual(headings["h2"], ["Subheading Section 1", "Subheading Section 2"])

    def test_extract_paragraphs(self):
        data = self.scraper.scrape("https://test.local", html_content=SAMPLE_HTML)
        paragraphs = data["paragraphs"]
        self.assertEqual(len(paragraphs), 2)
        self.assertIn("This is the first long paragraph with enough characters to be extracted properly.", paragraphs[0])

    def test_extract_links(self):
        data = self.scraper.scrape("https://test.local", html_content=SAMPLE_HTML)
        links = data["links"]
        self.assertEqual(len(links), 2)
        internal_link = [l for l in links if l["is_internal"]][0]
        external_link = [l for l in links if not l["is_internal"]][0]

        self.assertEqual(internal_link["text"], "About Us Page")
        self.assertEqual(internal_link["url"], "https://test.local/about-us")
        self.assertEqual(external_link["text"], "External Documentation")
        self.assertEqual(external_link["url"], "https://external.org/docs")

    def test_extract_images(self):
        data = self.scraper.scrape("https://test.local", html_content=SAMPLE_HTML)
        images = data["images"]
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0]["src"], "https://test.local/images/diagram.png")
        self.assertEqual(images[0]["alt"], "Architecture Diagram")

    def test_extract_tables(self):
        data = self.scraper.scrape("https://test.local", html_content=SAMPLE_HTML)
        tables = data["tables"]
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual(table["headers"], ["Item", "Qty", "Price"])
        self.assertEqual(len(table["rows"]), 2)
        self.assertEqual(table["rows"][0]["Item"], "Widget A")
        self.assertEqual(table["rows"][0]["Qty"], "10")
        self.assertEqual(table["rows"][0]["Price"], "$5.00")

    def test_custom_selector(self):
        data = self.scraper.scrape(
            "https://test.local",
            selector=".price",
            html_content=SAMPLE_HTML,
        )
        self.assertIn("custom_selector", data)
        matches = data["custom_selector"]["matches"]
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]["text"], "$19.99")
        self.assertEqual(matches[1]["text"], "$29.99")

    def test_custom_xpath_selector(self):
        data = self.scraper.scrape(
            "https://test.local",
            selector="//span[@class='price']",
            html_content=SAMPLE_HTML,
        )
        self.assertIn("custom_selector", data)
        matches = data["custom_selector"]["matches"]
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]["text"], "$19.99")
        self.assertEqual(matches[1]["text"], "$29.99")

    def test_case_insensitive_meta(self):
        html = """
        <html>
        <head>
            <meta name="Description" content="Upper case meta name">
            <meta name="KEYWORDS" content="test, uppercase">
            <link rel="CANONICAL" href="/upper-canonical">
        </head>
        <body><p>Hello world case test</p></body>
        </html>
        """
        data = self.scraper.scrape("https://test.local", html_content=html)
        self.assertEqual(data["metadata"]["description"], "Upper case meta name")
        self.assertEqual(data["metadata"]["keywords"], "test, uppercase")
        self.assertEqual(data["metadata"]["canonical_url"], "https://test.local/upper-canonical")

    def test_script_and_style_removal(self):
        html = """
        <html>
        <head><style>body { color: red; }</style></head>
        <body>
            <script>var x = 123; console.log(x);</script>
            <h1>Real Heading</h1>
            <p>Real paragraph text with enough content to be captured.</p>
        </body>
        </html>
        """
        data = self.scraper.scrape("https://test.local", html_content=html)
        self.assertEqual(data["headings"]["h1"], ["Real Heading"])
        text_out = format_as_text(data)
        self.assertNotIn("console.log", text_out)
        self.assertNotIn("color: red", text_out)

    def test_stealth_configuration(self):
        scraper_stealth = WebScraper(use_stealth=True)
        self.assertTrue(scraper_stealth.use_stealth)
        self.assertEqual(scraper_stealth.timeout, 15)

    def test_live_http_server(self):
        data = self.scraper.scrape(self.base_url)
        self.assertEqual(data["metadata"]["title"], "Sample Test Article")
        self.assertEqual(data["headings"]["h1"], ["Main Article Headline"])

    def test_convenience_function(self):
        data = scrape_url(self.base_url, selector=".item-name")
        self.assertEqual(len(data["custom_selector"]["matches"]), 2)
        self.assertEqual(data["custom_selector"]["matches"][0]["text"], "Python Handbook")

    def test_format_as_text(self):
        data = self.scraper.scrape("https://test.local", html_content=SAMPLE_HTML)
        text_out = format_as_text(data)
        self.assertIn("Sample Test Article", text_out)
        self.assertIn("Main Article Headline", text_out)
        self.assertIn("Widget A", text_out)

    def test_format_as_markdown(self):
        data = self.scraper.scrape("https://test.local", html_content=SAMPLE_HTML)
        md_out = format_as_markdown(data)
        self.assertIn("# Sample Test Article", md_out)
        self.assertIn("| Item | Qty | Price |", md_out)
        self.assertIn("[About Us Page](https://test.local/about-us)", md_out)

    def test_404_error_handling(self):
        with self.assertRaises(Exception):
            self.scraper.scrape(f"{self.base_url}/404")


    def test_dz_domain_detection(self):
        self.assertTrue(is_dz_domain("elmoudjahid.dz"))
        self.assertTrue(is_dz_domain("https://algerietelecom.com.dz/home"))
        self.assertTrue(is_dz_domain("http://www.univ-algiers.dz"))
        self.assertTrue(is_dz_domain("sub.domain.gov.dz"))
        self.assertFalse(is_dz_domain("google.com"))
        self.assertFalse(is_dz_domain("https://example.org/about"))
        self.assertFalse(is_dz_domain(""))

    def test_dz_data_extraction(self):
        sample_dz_html = """
        <html>
        <head><title>Algerian Business Portal</title></head>
        <body>
            <h1>Algerian Company</h1>
            <p>Notre siège est basé à Alger et nous opérons aussi à Oran et Constantine.</p>
            <p>Téléphone standard: +213 21 23 45 67 ou mobile: 0550 12 34 56.</p>
            <p>Identifiants officiels: NIF: 099812345678901 - NIS: 123456789012345 - RC: 16/00-1234567B16</p>
            <a href="https://partner.dz/services">Partenaire DZ</a>
            <a href="/local-link">Local Internal</a>
        </body>
        </html>
        """
        data = self.scraper.scrape(
            "https://business.dz",
            html_content=sample_dz_html,
            include_dz_data=True,
        )
        self.assertIn("dz_data", data)
        dz = data["dz_data"]
        self.assertTrue(dz["is_dz_website"])
        self.assertIn("Alger", dz["wilayas_detected"])
        self.assertIn("Oran", dz["wilayas_detected"])
        self.assertIn("Constantine", dz["wilayas_detected"])
        self.assertTrue(any("0550" in p or "213" in p for p in dz["algerian_phones"]))
        self.assertEqual(dz["commercial_identifiers"].get("nif"), "099812345678901")
        self.assertEqual(dz["commercial_identifiers"].get("nis"), "123456789012345")
        self.assertEqual(dz["commercial_identifiers"].get("rc"), "16/00-1234567B16")
        self.assertTrue(any(l["url"] == "https://partner.dz/services" for l in dz["discovered_dz_links"]))

    def test_dz_dns_info_structure(self):
        dns_info = get_dz_dns_info("https://test.local")
        self.assertEqual(dns_info["hostname"], "test.local")
        self.assertIn("has_dz_dns", dns_info)
        self.assertIn("nameservers", dns_info)
        self.assertIn("mail_servers", dns_info)

    def test_automatic_navigation_10_pages(self):
        start_url = f"{self.base_url}/nav/0"
        crawl_result = self.scraper.crawl(start_url, max_pages=10, delay=0.0)

        self.assertTrue(crawl_result["crawl_mode"])
        self.assertEqual(crawl_result["total_pages_crawled"], 10)
        self.assertEqual(len(crawl_result["pages"]), 10)
        self.assertEqual(crawl_result["max_pages_requested"], 10)

        # Check pages were navigated properly
        urls = [p["url"] for p in crawl_result["pages"]]
        self.assertEqual(len(set(urls)), 10)
        self.assertIn(start_url, urls)

        # Check aggregation
        agg = crawl_result["aggregated"]
        self.assertIn("h1", agg["all_headings"])
        self.assertTrue(len(agg["sample_paragraphs"]) > 0)
        self.assertIn("Alger", agg["wilayas_detected"])
        self.assertEqual(agg["commercial_identifiers"].get("nif"), "099812345678901")

    def test_crawl_website_convenience_function(self):
        start_url = f"{self.base_url}/nav/0"
        crawl_result = crawl_website(start_url, max_pages=5, delay=0.0)
        self.assertEqual(crawl_result["total_pages_crawled"], 5)
        self.assertEqual(len(crawl_result["pages"]), 5)

    def test_google_info_extraction(self):
        g_info = get_google_info("https://example.dz")
        self.assertEqual(g_info["target"], "example.dz")
        self.assertEqual(g_info["google_search_url"], "https://www.google.com/search?q=example.dz")
        self.assertEqual(g_info["google_site_search_url"], "https://www.google.com/search?q=site:example.dz")
        self.assertIn("about", g_info["google_section_searches"])
        self.assertIsInstance(g_info["google_related_queries"], list)
        self.assertIsInstance(g_info["google_related_urls"], list)

        # Test top-level fetch_google_info convenience function
        top_g = fetch_google_info("example.dz")
        self.assertEqual(top_g["target"], "example.dz")

    def test_format_as_text_and_markdown_crawl(self):
        start_url = f"{self.base_url}/nav/0"
        crawl_result = self.scraper.crawl(start_url, max_pages=3, delay=0.0, include_google_info=True)

        text_out = format_as_text(crawl_result)
        self.assertIn("AUTOMATIC NAVIGATION CRAWL RESULTS", text_out)
        self.assertIn("NAVIGATED PAGES", text_out)
        self.assertIn("AGGREGATED CRAWL SUMMARY", text_out)
        self.assertIn("GOOGLE INFOS & RELATED URLS", text_out)

        md_out = format_as_markdown(crawl_result)
        self.assertIn("# Automatic Navigation Crawl Report", md_out)
        self.assertIn("## Navigated Pages", md_out)
        self.assertIn("## Aggregated Findings Across Navigated Pages", md_out)
        self.assertIn("## Google Information & Related URLs", md_out)


if __name__ == "__main__":
    unittest.main(verbosity=2)

