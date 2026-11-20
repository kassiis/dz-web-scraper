#!/usr/bin/env python3
"""
Web Scraper for Small-Scale Web Data Extraction
------------------------------------------------
A lightweight, robust Python scraper for fetching and extracting data from a given URL.
Powered by Scrapling for high-performance, intelligent parsing and element selection.

Features:
- Extracts page metadata (title, description, keywords, OpenGraph tags, canonical URL)
- Extracts headings (h1-h4), paragraphs, links (resolved to absolute URLs), images, and tables
- Supports custom CSS selectors and XPath (e.g. `--selector ".price"` or `--selector "//span[@class='price']"`)
- Formats output as human-readable text, structured JSON, or Markdown
- Realistic browser headers, timeout controls, and error handling
- Optional stealth fetching via Scrapling Fetcher
- Can be used both as a CLI tool and an importable Python library
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import socket
import sys
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urljoin, urlparse

try:
    import requests
    from scrapling import Selector
except ImportError as err:
    print(
        f"Missing required dependency: {err}\n"
        "Please install requirements using: pip install scrapling requests",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from scrapling import Fetcher, StealthyFetcher
    HAS_SCRAPLING_FETCHER = True
except ImportError:
    Fetcher = None
    StealthyFetcher = None
    HAS_SCRAPLING_FETCHER = False


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Algerian Phone Number Regex: +213 / 00213 / 02X / 03X / 04X / 05X / 06X / 07X / 09X
DZ_PHONE_REGEX = re.compile(
    r"(?:\+213|00213|0)\s*(?:\(0\)\s*)?(?:[234][0-9]|[5679][0-9])(?:[\s\.\-]?[0-9]{2}){3}"
)

# Comprehensive list of Algerian Wilayas (provinces)
ALGERIAN_WILAYAS: List[str] = [
    "Adrar", "Chlef", "Laghouat", "Oum El Bouaghi", "Batna", "Béjaïa", "Bejaia", "Biskra",
    "Béchar", "Bechar", "Blida", "Bouira", "Tamanrasset", "Tébessa", "Tebessa", "Tlemcen",
    "Tiaret", "Tizi Ouzou", "Alger", "Algiers", "Djelfa", "Jijel", "Sétif", "Setif",
    "Saïda", "Saida", "Skikda", "Sidi Bel Abbès", "Sidi Bel Abbes", "Annaba", "Guelma",
    "Constantine", "Médéa", "Medea", "Mostaganem", "M'Sila", "Msila", "Mascara", "Ouargla",
    "Oran", "El Bayadh", "Illizi", "Bordj Bou Arréridj", "Bordj Bou Arreridj", "Boumerdès",
    "Boumerdes", "El Tarf", "Tindouf", "Tissemsilt", "El Oued", "Khenchela", "Souk Ahras",
    "Tipaza", "Mila", "Aïn Defla", "Ain Defla", "Naâma", "Naama", "Aïn Témouchent",
    "Ain Temouchent", "Ghardaïa", "Ghardaia", "Relizane", "Timimoun", "Bordj Badji Mokhtar",
    "Ouled Djellal", "Béni Abbès", "In Salah", "In Guezzam", "Touggourt", "Djanet",
    "El M'Ghair", "El Menia"
]


def is_dz_domain(domain_or_url: str) -> bool:
    """
    Determines if a URL or hostname belongs to an Algerian .dz domain (ccTLD .dz).
    Examples: elmoudjahid.dz, algerietelecom.com.dz, univ-algiers.dz, gov.dz
    """
    if not domain_or_url:
        return False
    parsed = urlparse(domain_or_url)
    host = (parsed.netloc or parsed.path or domain_or_url).split(":")[0].strip().lower()
    return host.endswith(".dz") or host == "dz"


def get_dz_dns_info(domain_or_url: str, timeout: float = 3.0) -> Dict[str, Any]:
    """
    Performs DNS resolution on a domain and checks for .dz DNS indicators,
    including canonical name, aliases, IP addresses, nameservers, and mail servers.
    """
    parsed = urlparse(domain_or_url)
    host = (parsed.netloc or parsed.path or domain_or_url).split(":")[0].strip().lower()
    is_dz = is_dz_domain(host)

    dns_info: Dict[str, Any] = {
        "hostname": host,
        "is_dz_domain": is_dz,
        "resolved": False,
        "canonical_name": None,
        "aliases": [],
        "ip_addresses": [],
        "nameservers": [],
        "mail_servers": [],
        "has_dz_dns": is_dz,
    }

    if not host or host == "localhost" or host.startswith("127.") or host.endswith(".local"):
        return dns_info

    orig_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        canonical, aliases, ips = socket.gethostbyname_ex(host)
        dns_info["resolved"] = True
        dns_info["canonical_name"] = canonical
        dns_info["aliases"] = aliases
        dns_info["ip_addresses"] = ips
        if canonical.lower().endswith(".dz") or any(a.lower().endswith(".dz") for a in aliases):
            dns_info["has_dz_dns"] = True
        elif ips and not dns_info["has_dz_dns"]:
            try:
                ptr_name, ptr_aliases, _ = socket.gethostbyaddr(ips[0])
                if ptr_name.lower().endswith(".dz") or any(pa.lower().endswith(".dz") for pa in ptr_aliases):
                    dns_info["has_dz_dns"] = True
                    dns_info["ptr_record"] = ptr_name
            except Exception:
                pass
    except Exception as exc:
        dns_info["error"] = str(exc)
    finally:
        socket.setdefaulttimeout(orig_timeout)

    try:
        for rtype, key in [("NS", "nameservers"), ("MX", "mail_servers")]:
            res = requests.get(
                f"https://dns.google/resolve?name={host}&type={rtype}",
                timeout=timeout,
            )
            if res.status_code == 200:
                answer = res.json().get("Answer", [])
                for ans in answer:
                    val = ans.get("data", "").strip(".")
                    if val and val not in dns_info[key]:
                        dns_info[key].append(val)
                        if val.lower().endswith(".dz"):
                            dns_info["has_dz_dns"] = True
    except Exception:
        pass

    return dns_info


def get_google_info(domain_or_url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """
    Retrieves Google information and URLs related to the target website:
    - Direct Google search, site search, and cache URLs
    - Google Autocomplete / Query suggestions related to the website
    - Direct navigational and section URLs discovered via Google
    - Section search links (contact, about, services, login)
    """
    parsed = urlparse(domain_or_url)
    domain = (parsed.netloc or parsed.path or domain_or_url).split(":")[0].strip().lower()

    google_info: Dict[str, Any] = {
        "target": domain,
        "google_search_url": f"https://www.google.com/search?q={domain}",
        "google_site_search_url": f"https://www.google.com/search?q=site:{domain}",
        "google_cache_url": f"https://webcache.googleusercontent.com/search?q=cache:{domain}",
        "google_related_queries": [],
        "google_related_urls": [],
        "google_section_searches": {
            "about": f"https://www.google.com/search?q=site:{domain}+about",
            "contact": f"https://www.google.com/search?q=site:{domain}+contact",
            "services": f"https://www.google.com/search?q=site:{domain}+services+OR+products",
            "login": f"https://www.google.com/search?q=site:{domain}+login+OR+portal",
        },
    }

    if not domain or domain == "localhost" or domain.startswith("127.") or domain.endswith(".local"):
        return google_info

    try:
        url = f"https://suggestqueries.google.com/complete/search?client=chrome&q={domain}"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            suggestions = data[1] if len(data) > 1 else []
            for sugg in suggestions:
                if sugg and sugg not in google_info["google_related_queries"]:
                    google_info["google_related_queries"].append(sugg)

                # Check if suggestion represents a URL
                if sugg.startswith(("http://", "https://")):
                    if sugg not in google_info["google_related_urls"]:
                        google_info["google_related_urls"].append(sugg)
                elif domain in sugg and ("/" in sugg or sugg.startswith("www.")):
                    url_cand = "https://" + sugg.lstrip("/")
                    if url_cand not in google_info["google_related_urls"]:
                        google_info["google_related_urls"].append(url_cand)
    except Exception as exc:
        google_info["error"] = str(exc)

    return google_info


def extract_dz_data(
    page: Selector,
    base_url: str,
    dns_timeout: float = 3.0,
    raw_html: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extracts data specific to Algerian .dz websites, including DNS resolution,
    Algerian phone numbers, wilaya mentions, commercial identifiers, and discovered .dz links.
    """
    dns_data = get_dz_dns_info(base_url, timeout=dns_timeout)
    raw_text = raw_html or page.get_all_text()

    # Extract Algerian phone numbers (+213 / 00213 / 02X / 03X / 04X / 05X / 06X / 07X / 09X)
    phone_matches: set[str] = set()
    for match in DZ_PHONE_REGEX.finditer(raw_text):
        clean_num = re.sub(r"\s+", " ", match.group(0)).strip()
        digits = re.sub(r"\D", "", clean_num)
        if 9 <= len(digits) <= 12:
            phone_matches.add(clean_num)

    # Extract Wilaya mentions
    wilayas_found: List[str] = []
    text_lower = raw_text.lower()
    for w in ALGERIAN_WILAYAS:
        pattern = r"\b" + re.escape(w.lower()) + r"\b"
        if re.search(pattern, text_lower) and w not in wilayas_found:
            wilayas_found.append(w)

    # Extract discovered .dz links
    dz_links: List[Dict[str, str]] = []
    seen_links: set[str] = set()
    for a in page.css("a[href]"):
        href = a.attrib.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        resolved = urljoin(base_url, href)
        if is_dz_domain(resolved) and resolved not in seen_links:
            seen_links.add(resolved)
            dz_links.append({"text": a.get_all_text().strip(), "url": resolved})

    # Extract commercial and administrative IDs (NIF, NIS, RC)
    commercial_ids: Dict[str, str] = {}
    nif_match = re.search(r"\bNIF\s*[:\.]?\s*([0-9]{15,20})\b", raw_text, re.I)
    if nif_match:
        commercial_ids["nif"] = nif_match.group(1)
    nis_match = re.search(r"\bNIS\s*[:\.]?\s*([0-9]{10,20})\b", raw_text, re.I)
    if nis_match:
        commercial_ids["nis"] = nis_match.group(1)
    rc_match = re.search(r"\bRC\s*[:\.]?\s*([0-9A-Za-z\/\-\s]{6,25})\b", raw_text, re.I)
    if rc_match:
        commercial_ids["rc"] = rc_match.group(1).strip()

    is_dz_site = dns_data["has_dz_dns"] or bool(dz_links) or bool(phone_matches) or bool(commercial_ids)

    return {
        "is_dz_website": is_dz_site,
        "dns": dns_data,
        "algerian_phones": sorted(list(phone_matches)),
        "wilayas_detected": wilayas_found,
        "discovered_dz_links": dz_links,
        "commercial_identifiers": commercial_ids,
    }


class WebScraper:
    """Scrapes structured and targeted content from a web page using Scrapling."""

    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: int = 15,
        verify_ssl: bool = True,
        use_stealth: bool = False,
    ):
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.use_stealth = use_stealth
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def normalize_url(self, url: str) -> str:
        """Ensures the URL has a proper scheme."""
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return "https://" + url
        return url

    def fetch(self, url: str) -> str:
        """Fetches the raw HTML content from the given URL."""
        normalized_url = self.normalize_url(url)

        if self.use_stealth and HAS_SCRAPLING_FETCHER and Fetcher is not None:
            response = Fetcher.get(normalized_url, timeout=self.timeout)
            if response.status >= 400:
                raise requests.exceptions.HTTPError(
                    f"HTTP Error {response.status} while fetching {normalized_url}"
                )
            return response.html_content or response.text or ""

        response = self.session.get(
            normalized_url,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        response.raise_for_status()

        if response.encoding is None or response.encoding == "ISO-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"

        return response.text

    @staticmethod
    def _clean_text(text: Optional[str]) -> str:
        """Trims whitespace and collapses excessive internal whitespace."""
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def extract_metadata(self, page: Selector, base_url: str) -> Dict[str, Any]:
        """Extracts page title, meta description, keywords, OpenGraph data, and canonical URL."""
        meta_data: Dict[str, Any] = {}

        # Title
        title_tag = page.css("title")
        meta_data["title"] = self._clean_text(title_tag[0].get_all_text()) if title_tag else ""

        # Description (case-insensitive name="description", or fallback to og:description)
        desc = page.xpath(
            '//meta[translate(@name, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")="description"]/@content'
        ).get()
        if not desc:
            desc = page.xpath('//meta[@property="og:description"]/@content').get()
        meta_data["description"] = desc.strip() if desc else ""

        # Keywords (case-insensitive name="keywords")
        kw = page.xpath(
            '//meta[translate(@name, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")="keywords"]/@content'
        ).get()
        meta_data["keywords"] = kw.strip() if kw else ""

        # Canonical URL (case-insensitive rel="canonical")
        canon_href = page.xpath(
            '//link[translate(@rel, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")="canonical"]/@href'
        ).get()
        if canon_href and canon_href.strip():
            meta_data["canonical_url"] = urljoin(base_url, canon_href.strip())
        else:
            meta_data["canonical_url"] = base_url

        # OpenGraph details
        og_data: Dict[str, str] = {}
        for og_prop in ("og:title", "og:type", "og:image", "og:url", "og:site_name"):
            val = page.xpath(f'//meta[@property="{og_prop}"]/@content').get()
            if val and val.strip():
                og_data[og_prop] = val.strip()
        if og_data:
            meta_data["open_graph"] = og_data

        return meta_data

    def extract_headings(self, page: Selector) -> Dict[str, List[str]]:
        """Extracts h1, h2, h3, and h4 headings from the page."""
        headings: Dict[str, List[str]] = {}
        for level in ("h1", "h2", "h3", "h4"):
            items: List[str] = []
            for tag in page.css(level):
                cleaned = self._clean_text(tag.get_all_text())
                if cleaned and cleaned not in items:
                    items.append(cleaned)
            if items:
                headings[level] = items
        return headings

    def extract_paragraphs(self, page: Selector, max_count: int = 50) -> List[str]:
        """Extracts non-empty paragraph text from the page."""
        paragraphs: List[str] = []
        for p in page.css("p"):
            text = self._clean_text(p.get_all_text())
            if len(text) > 20 and text not in paragraphs:
                paragraphs.append(text)
                if len(paragraphs) >= max_count:
                    break
        return paragraphs

    def extract_links(
        self, page: Selector, base_url: str, max_count: int = 50
    ) -> List[Dict[str, Any]]:
        """Extracts unique links with anchor text and absolute URLs."""
        links: List[Dict[str, Any]] = []
        seen_urls = set()
        base_domain = urlparse(base_url).netloc.lower()

        for a_tag in page.css("a[href]"):
            raw_href = a_tag.attrib.get("href", "").strip()
            if not raw_href or raw_href.startswith(("javascript:", "mailto:", "tel:", "#")):
                continue

            absolute_url = urljoin(base_url, raw_href)
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)

            anchor_text = self._clean_text(a_tag.get_all_text())
            link_domain = urlparse(absolute_url).netloc.lower()
            is_internal = link_domain == base_domain or link_domain.endswith("." + base_domain)

            links.append(
                {
                    "text": anchor_text or "[No text]",
                    "url": absolute_url,
                    "is_internal": is_internal,
                }
            )

            if len(links) >= max_count:
                break

        return links

    def extract_images(
        self, page: Selector, base_url: str, max_count: int = 25
    ) -> List[Dict[str, str]]:
        """Extracts image source URLs and alt descriptions."""
        images: List[Dict[str, str]] = []
        seen_srcs = set()

        for img in page.css("img"):
            src = img.attrib.get("src") or img.attrib.get("data-src")
            if not src:
                continue

            absolute_src = urljoin(base_url, src.strip())
            if absolute_src in seen_srcs:
                continue
            seen_srcs.add(absolute_src)

            images.append(
                {
                    "src": absolute_src,
                    "alt": self._clean_text(img.attrib.get("alt", "")),
                }
            )

            if len(images) >= max_count:
                break

        return images

    def extract_tables(self, page: Selector, max_tables: int = 5) -> List[Dict[str, Any]]:
        """Extracts tabular data as structured lists of dictionaries."""
        tables_data: List[Dict[str, Any]] = []

        for table_idx, table in enumerate(page.css("table")[:max_tables]):
            all_trs = table.css("tr")
            if not all_trs:
                continue

            headers: List[str] = []
            rows: List[Any] = []

            # Headers from first row
            header_row = all_trs[0]
            th_tags = header_row.css("th, td")
            headers = [self._clean_text(th.get_all_text()) for th in th_tags]

            # Subsequent rows
            for tr in all_trs[1 if headers else 0:]:
                tds = tr.css("td, th")
                row_values = [self._clean_text(td.get_all_text()) for td in tds]
                if not any(row_values):
                    continue

                if headers and len(headers) == len(row_values):
                    rows.append(dict(zip(headers, row_values)))
                else:
                    rows.append(row_values)

            if rows:
                tables_data.append(
                    {
                        "table_index": table_idx + 1,
                        "headers": headers,
                        "rows": rows,
                    }
                )

        return tables_data

    def extract_by_selector(
        self, page: Selector, selector: str, max_count: int = 50
    ) -> List[Dict[str, Any]]:
        """Extracts elements matching a custom CSS or XPath selector."""
        matched: List[Dict[str, Any]] = []

        # Support both XPath and CSS selectors
        if selector.startswith(("/", "./", "(//")):
            elements = page.xpath(selector)[:max_count]
        else:
            elements = page.css(selector)[:max_count]

        for el in elements:
            attribs = getattr(el, "attrib", {})
            matched.append(
                {
                    "tag": getattr(el, "tag", ""),
                    "text": self._clean_text(el.get_all_text()),
                    "attributes": {
                        k: v for k, v in attribs.items() if k in ("class", "id", "href", "src")
                    },
                }
            )
        return matched

    def scrape(
        self,
        url: str,
        selector: Optional[str] = None,
        html_content: Optional[str] = None,
        include_dz_data: bool = True,
        include_google_info: bool = False,
    ) -> Dict[str, Any]:
        """
        Scrapes data from the given URL or raw HTML string.

        Args:
            url: The URL to scrape.
            selector: Optional CSS or XPath selector to query specific elements.
            html_content: Optional pre-fetched HTML string (useful for testing or cached data).
            include_dz_data: Collect Algerian .dz DNS / phone / wilaya information.
            include_google_info: Collect Google info and related URLs for the domain.

        Returns:
            Dictionary containing scraped metadata, headings, paragraphs, links, images, tables, etc.
        """
        normalized_url = self.normalize_url(url)
        raw_html = html_content if html_content is not None else self.fetch(normalized_url)
        page = Selector(raw_html)

        # Remove script, style, noscript, and svg elements to keep data clean
        for element in page.css("script, style, noscript, svg"):
            try:
                element._root.drop_tree()
            except Exception:
                pass

        data: Dict[str, Any] = {
            "url": normalized_url,
            "metadata": self.extract_metadata(page, normalized_url),
            "headings": self.extract_headings(page),
            "paragraphs": self.extract_paragraphs(page),
            "links": self.extract_links(page, normalized_url),
            "images": self.extract_images(page, normalized_url),
            "tables": self.extract_tables(page),
        }

        if selector:
            data["custom_selector"] = {
                "query": selector,
                "matches": self.extract_by_selector(page, selector),
            }

        if include_dz_data:
            data["dz_data"] = extract_dz_data(page, normalized_url, raw_html=raw_html)

        if include_google_info:
            data["google_info"] = get_google_info(normalized_url)

        return data

    def crawl(
        self,
        start_url: str,
        max_pages: int = 10,
        selector: Optional[str] = None,
        delay: float = 0.5,
        include_dz_data: bool = True,
        include_google_info: bool = False,
    ) -> Dict[str, Any]:
        """
        Automatically navigates through related pages of a website starting from start_url.
        Crawls up to max_pages (default: 10) related pages within the same website domain.
        """
        normalized_start = self.normalize_url(start_url)
        start_domain = urlparse(normalized_start).netloc.lower()

        visited_urls: Set[str] = set()
        queue: collections.deque[str] = collections.deque([normalized_start])
        pages_crawled: List[Dict[str, Any]] = []

        all_headings: Dict[str, List[str]] = collections.defaultdict(list)
        sample_paras: List[str] = []
        all_internal_links: Set[str] = set()
        all_external_links: Set[str] = set()
        all_images: List[Dict[str, str]] = []
        dz_phones: Set[str] = set()
        wilayas: Set[str] = set()
        commercial_ids: Dict[str, str] = {}
        dz_links: List[Dict[str, str]] = []

        skip_exts = (
            ".pdf", ".zip", ".rar", ".gz", ".tar", ".7z", ".png", ".jpg", ".jpeg",
            ".gif", ".webp", ".svg", ".ico", ".css", ".js", ".mp3", ".mp4", ".woff", ".woff2"
        )

        while queue and len(pages_crawled) < max_pages:
            cur = queue.popleft()
            p = urlparse(cur)
            clean_url = f"{p.scheme}://{p.netloc}{p.path}" + (f"?{p.query}" if p.query else "")
            if clean_url in visited_urls:
                continue
            visited_urls.add(clean_url)

            try:
                page_data = self.scrape(cur, selector=selector, include_dz_data=include_dz_data)
                title = page_data.get("metadata", {}).get("title", "") or clean_url
                pages_crawled.append({
                    "page_number": len(pages_crawled) + 1,
                    "url": clean_url,
                    "title": title,
                    "data": page_data,
                })

                for lvl, items in page_data.get("headings", {}).items():
                    for it in items:
                        if it not in all_headings[lvl]:
                            all_headings[lvl].append(it)

                for para in page_data.get("paragraphs", [])[:2]:
                    if para not in sample_paras and len(sample_paras) < 10:
                        sample_paras.append(para)

                for img in page_data.get("images", []):
                    if not any(x["src"] == img["src"] for x in all_images):
                        all_images.append(img)

                for lnk in page_data.get("links", []):
                    l_url = lnk.get("url", "")
                    if lnk.get("is_internal"):
                        all_internal_links.add(l_url)
                        lp = urlparse(l_url)
                        if (lp.netloc.lower() == start_domain or lp.netloc.lower().endswith("." + start_domain)) and not any(lp.path.lower().endswith(x) for x in skip_exts):
                            norm_nav = f"{lp.scheme}://{lp.netloc}{lp.path}" + (f"?{lp.query}" if lp.query else "")
                            if norm_nav not in visited_urls and norm_nav not in queue:
                                queue.append(norm_nav)
                    else:
                        all_external_links.add(l_url)

                dz_info = page_data.get("dz_data", {})
                if dz_info:
                    dz_phones.update(dz_info.get("algerian_phones", []))
                    wilayas.update(dz_info.get("wilayas_detected", []))
                    for k, v in dz_info.get("commercial_identifiers", {}).items():
                        commercial_ids.setdefault(k, v)
                    for dz_l in dz_info.get("discovered_dz_links", []):
                        if not any(x["url"] == dz_l["url"] for x in dz_links):
                            dz_links.append(dz_l)

            except Exception as e:
                pages_crawled.append({
                    "page_number": len(pages_crawled) + 1,
                    "url": clean_url,
                    "title": "[Error Fetching Page]",
                    "error": str(e),
                })

            if len(pages_crawled) < max_pages and queue and delay > 0:
                time.sleep(delay)

        google_data = get_google_info(start_domain) if include_google_info else None

        aggregated = {
            "all_headings": dict(all_headings),
            "sample_paragraphs": sample_paras,
            "total_internal_links_count": len(all_internal_links),
            "total_external_links_count": len(all_external_links),
            "images_discovered_count": len(all_images),
            "images": all_images[:20],
            "algerian_phones": sorted(list(dz_phones)),
            "wilayas_detected": sorted(list(wilayas)),
            "commercial_identifiers": commercial_ids,
            "discovered_dz_links": dz_links,
        }

        return {
            "crawl_mode": True,
            "start_url": normalized_start,
            "domain": start_domain,
            "total_pages_crawled": len(pages_crawled),
            "max_pages_requested": max_pages,
            "visited_urls": sorted(list(visited_urls)),
            "pages": pages_crawled,
            "aggregated": aggregated,
            "google_info": google_data,
        }



def _format_crawl_as_text(data: Dict[str, Any]) -> str:
    """Formats multi-page crawl navigation results as human-readable plain text."""
    lines: List[str] = []
    lines.append("=" * 70)
    lines.append(f"AUTOMATIC NAVIGATION CRAWL RESULTS: {data.get('start_url')}")
    lines.append(f"Pages Navigated: {data.get('total_pages_crawled', 0)} / {data.get('max_pages_requested', 10)}")
    lines.append("=" * 70)

    pages = data.get("pages", [])
    if pages:
        lines.append("\n[NAVIGATED PAGES]")
        for p in pages:
            pnum = p.get("page_number", "-")
            ptitle = p.get("title", "No Title")
            purl = p.get("url", "")
            err = f" (Error: {p.get('error')})" if "error" in p else ""
            lines.append(f"  {pnum}. {ptitle} -> {purl}{err}")

    agg = data.get("aggregated", {})
    if agg:
        lines.append("\n[AGGREGATED CRAWL SUMMARY]")
        lines.append(f"  Internal Links Discovered: {agg.get('total_internal_links_count', 0)}")
        lines.append(f"  External Links Discovered: {agg.get('total_external_links_count', 0)}")
        lines.append(f"  Images Discovered:         {agg.get('images_discovered_count', 0)}")

        all_h = agg.get("all_headings", {})
        if all_h:
            lines.append("\n[KEY DISCOVERED HEADINGS]")
            for lvl, items in all_h.items():
                for h in items[:4]:
                    lines.append(f"  - [{lvl.upper()}] {h}")

        paras = agg.get("sample_paragraphs", [])
        if paras:
            lines.append("\n[SAMPLE CONTENT PARAGRAPHS]")
            for idx, p in enumerate(paras[:4], start=1):
                lines.append(f"  {idx}. {p}")

        phones = agg.get("algerian_phones", [])
        wilayas = agg.get("wilayas_detected", [])
        cids = agg.get("commercial_identifiers", {})
        dz_links = agg.get("discovered_dz_links", [])

        if phones or wilayas or cids or dz_links:
            lines.append("\n[AGGREGATED ALGERIAN .DZ DATA]")
            if phones:
                lines.append(f"  Algerian Phones:   {', '.join(phones)}")
            if wilayas:
                lines.append(f"  Wilayas Mentioned: {', '.join(wilayas)}")
            if cids:
                lines.append("  Commercial IDs:")
                for k, v in cids.items():
                    lines.append(f"    {k.upper()}: {v}")
            if dz_links:
                lines.append(f"  Discovered .dz URLs ({len(dz_links)} total):")
                for dl in dz_links[:5]:
                    lines.append(f"    - {dl.get('text', '')} -> {dl.get('url', '')}")

    g_info = data.get("google_info")
    if g_info:
        lines.append("\n[GOOGLE INFOS & RELATED URLS]")
        lines.append(f"  Google Search URL     : {g_info.get('google_search_url')}")
        lines.append(f"  Google Site Search    : {g_info.get('google_site_search_url')}")
        lines.append(f"  Google Cache URL      : {g_info.get('google_cache_url')}")
        queries = g_info.get("google_related_queries", [])
        if queries:
            lines.append("  Google Related Queries:")
            for q in queries[:6]:
                lines.append(f"    - {q}")
        rel_urls = g_info.get("google_related_urls", [])
        if rel_urls:
            lines.append("  Google Related URLs:")
            for u in rel_urls[:6]:
                lines.append(f"    - {u}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)



def format_as_text(data: Dict[str, Any]) -> str:
    """Formats scraped data as human-readable plain text."""
    if data.get("crawl_mode"):
        return _format_crawl_as_text(data)

    lines: List[str] = []
    lines.append("=" * 70)
    lines.append(f"SCRAPED DATA FOR: {data.get('url', 'N/A')}")
    lines.append("=" * 70)

    # Metadata
    meta = data.get("metadata", {})
    lines.append("\n[METADATA]")
    lines.append(f"  Title      : {meta.get('title') or '(none)'}")
    lines.append(f"  Description: {meta.get('description') or '(none)'}")
    if meta.get("keywords"):
        lines.append(f"  Keywords   : {meta.get('keywords')}")
    if meta.get("open_graph"):
        lines.append("  OpenGraph  :")
        for k, v in meta["open_graph"].items():
            lines.append(f"    {k}: {v}")

    # Custom selector if present
    if "custom_selector" in data:
        cs = data["custom_selector"]
        lines.append(f"\n[CUSTOM SELECTOR: '{cs.get('query')}'] ({len(cs.get('matches', []))} matches)")
        for idx, match in enumerate(cs.get("matches", []), start=1):
            lines.append(f"  {idx}. <{match.get('tag')}> {match.get('text')}")

    # Headings
    headings = data.get("headings", {})
    if headings:
        lines.append("\n[HEADINGS]")
        for lvl, items in headings.items():
            lines.append(f"  {lvl.upper()}:")
            for h in items:
                lines.append(f"    - {h}")

    # Paragraphs
    paragraphs = data.get("paragraphs", [])
    if paragraphs:
        lines.append(f"\n[PARAGRAPHS] (Showing first {min(len(paragraphs), 5)} of {len(paragraphs)})")
        for idx, p in enumerate(paragraphs[:5], start=1):
            lines.append(f"  {idx}. {p}")

    # Tables
    tables = data.get("tables", [])
    if tables:
        lines.append(f"\n[TABLES] ({len(tables)} found)")
        for t in tables:
            lines.append(f"  Table #{t.get('table_index')} (Columns: {', '.join(t.get('headers', []))})")
            for row in t.get("rows", [])[:3]:
                lines.append(f"    Row: {row}")
            if len(t.get("rows", [])) > 3:
                lines.append(f"    ... {len(t.get('rows')) - 3} more row(s)")

    # Links
    links = data.get("links", [])
    if links:
        lines.append(f"\n[LINKS] (Showing first {min(len(links), 8)} of {len(links)})")
        for lnk in links[:8]:
            tag = "Internal" if lnk.get("is_internal") else "External"
            lines.append(f"  - [{tag}] {lnk.get('text')} -> {lnk.get('url')}")

    # Images
    images = data.get("images", [])
    if images:
        lines.append(f"\n[IMAGES] (Showing first {min(len(images), 5)} of {len(images)})")
        for img in images[:5]:
            alt = f" (alt: '{img['alt']}')" if img.get("alt") else ""
            lines.append(f"  - {img.get('src')}{alt}")

    # DZ Data & DNS Info
    dz = data.get("dz_data")
    if dz:
        dns = dz.get("dns", {})
        has_dz = dz.get("is_dz_website") or dns.get("has_dz_dns")
        if has_dz or dz.get("algerian_phones") or dz.get("wilayas_detected"):
            lines.append("\n[ALGERIAN .DZ DATA & DNS INFO]")
            lines.append(f"  Has .dz DNS / Domain : {'YES' if dns.get('has_dz_dns') else 'NO'}")
            lines.append(f"  Resolved Hostname    : {dns.get('hostname')}")
            if dns.get("canonical_name"):
                lines.append(f"  Canonical (CNAME)    : {dns.get('canonical_name')}")
            if dns.get("ip_addresses"):
                lines.append(f"  IP Addresses         : {', '.join(dns.get('ip_addresses'))}")
            if dns.get("nameservers"):
                lines.append(f"  Nameservers          : {', '.join(dns.get('nameservers'))}")
            if dz.get("algerian_phones"):
                lines.append(f"  Algerian Phones      : {', '.join(dz.get('algerian_phones'))}")
            if dz.get("wilayas_detected"):
                lines.append(f"  Wilayas Detected     : {', '.join(dz.get('wilayas_detected'))}")
            cids = dz.get("commercial_identifiers", {})
            if cids:
                lines.append("  Commercial IDs       :")
                for k, v in cids.items():
                    lines.append(f"    {k.upper()}: {v}")
            dz_l = dz.get("discovered_dz_links", [])
            if dz_l:
                lines.append(f"  Discovered .dz Links : {len(dz_l)} link(s)")
                for dl in dz_l[:5]:
                    lines.append(f"    - {dl.get('text')} -> {dl.get('url')}")

    # Google Info
    g_info = data.get("google_info")
    if g_info:
        lines.append("\n[GOOGLE INFOS & RELATED URLS]")
        lines.append(f"  Google Search URL     : {g_info.get('google_search_url')}")
        lines.append(f"  Google Site Search    : {g_info.get('google_site_search_url')}")
        lines.append(f"  Google Cache URL      : {g_info.get('google_cache_url')}")
        queries = g_info.get("google_related_queries", [])
        if queries:
            lines.append("  Google Related Queries:")
            for q in queries[:6]:
                lines.append(f"    - {q}")
        rel_urls = g_info.get("google_related_urls", [])
        if rel_urls:
            lines.append("  Google Related URLs:")
            for u in rel_urls[:6]:
                lines.append(f"    - {u}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def _format_crawl_as_markdown(data: Dict[str, Any]) -> str:
    """Formats multi-page crawl navigation results into clean Markdown."""
    lines: List[str] = []
    start_url = data.get("start_url", "")
    lines.append(f"# Automatic Navigation Crawl Report: {start_url}\n")
    lines.append(f"**Domain:** `{data.get('domain')}`  ")
    lines.append(f"**Pages Navigated:** {data.get('total_pages_crawled', 0)} of max {data.get('max_pages_requested', 10)}\n")

    pages = data.get("pages", [])
    if pages:
        lines.append("## Navigated Pages\n")
        lines.append("| # | Title | URL |")
        lines.append("|---|---|---|")
        for p in pages:
            lines.append(f"| {p.get('page_number')} | {p.get('title')} | [{p.get('url')}]({p.get('url')}) |")
        lines.append("")

    agg = data.get("aggregated", {})
    if agg:
        lines.append("## Aggregated Findings Across Navigated Pages\n")
        lines.append(f"- **Internal Links Discovered:** {agg.get('total_internal_links_count', 0)}")
        lines.append(f"- **External Links Discovered:** {agg.get('total_external_links_count', 0)}")
        lines.append(f"- **Images Discovered:** {agg.get('images_discovered_count', 0)}\n")

        all_h = agg.get("all_headings", {})
        if all_h:
            lines.append("### Key Discovered Headings\n")
            for lvl, items in all_h.items():
                for h in items[:4]:
                    lines.append(f"- **{lvl.upper()}**: {h}")
            lines.append("")

        phones = agg.get("algerian_phones", [])
        wilayas = agg.get("wilayas_detected", [])
        cids = agg.get("commercial_identifiers", {})
        dz_links = agg.get("discovered_dz_links", [])

        if phones or wilayas or cids or dz_links:
            lines.append("### Algerian (.dz) Website Details\n")
            if phones:
                lines.append(f"- **Algerian Phone Numbers:** {', '.join(phones)}")
            if wilayas:
                lines.append(f"- **Wilayas Detected:** {', '.join(wilayas)}")
            if cids:
                lines.append("- **Commercial & Administrative Identifiers:**")
                for k, v in cids.items():
                    lines.append(f"  - **{k.upper()}**: `{v}`")
            if dz_links:
                lines.append(f"- **Discovered .dz Links ({len(dz_links)} total):**")
                for dl in dz_links[:6]:
                    lines.append(f"  - [{dl.get('text')}]({dl.get('url')})")
            lines.append("")

    g_info = data.get("google_info")
    if g_info:
        lines.append("## Google Information & Related URLs\n")
        lines.append(f"- **Google Search:** [{g_info.get('google_search_url')}]({g_info.get('google_search_url')})")
        lines.append(f"- **Google Site Search:** [{g_info.get('google_site_search_url')}]({g_info.get('google_site_search_url')})")
        lines.append(f"- **Google Web Cache:** [{g_info.get('google_cache_url')}]({g_info.get('google_cache_url')})\n")
        queries = g_info.get("google_related_queries", [])
        if queries:
            lines.append("### Google Related Queries\n")
            for q in queries[:6]:
                lines.append(f"- {q}")
            lines.append("")
        rel_urls = g_info.get("google_related_urls", [])
        if rel_urls:
            lines.append("### Google Discovered Related URLs\n")
            for u in rel_urls[:6]:
                lines.append(f"- [{u}]({u})")
            lines.append("")

    return "\n".join(lines)



def format_as_markdown(data: Dict[str, Any]) -> str:
    """Formats scraped data into clean Markdown."""
    if data.get("crawl_mode"):
        return _format_crawl_as_markdown(data)

    lines: List[str] = []
    meta = data.get("metadata", {})
    title = meta.get("title") or "Scraped Page"

    lines.append(f"# {title}")
    lines.append(f"**Source URL:** [{data.get('url')}]({data.get('url')})\n")

    if meta.get("description"):
        lines.append(f"> {meta.get('description')}\n")

    if "custom_selector" in data:
        cs = data["custom_selector"]
        lines.append(f"## Custom Selector Matches (`{cs.get('query')}`)\n")
        for match in cs.get("matches", []):
            lines.append(f"- **{match.get('tag')}**: {match.get('text')}")
        lines.append("")

    headings = data.get("headings", {})
    if headings:
        lines.append("## Headings\n")
        for lvl, items in headings.items():
            for item in items:
                lines.append(f"- **{lvl.upper()}**: {item}")
        lines.append("")

    paragraphs = data.get("paragraphs", [])
    if paragraphs:
        lines.append("## Content\n")
        for p in paragraphs:
            lines.append(f"{p}\n")

    tables = data.get("tables", [])
    if tables:
        lines.append("## Tables\n")
        for t in tables:
            headers = t.get("headers", [])
            if headers:
                lines.append("| " + " | ".join(headers) + " |")
                lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                for row in t.get("rows", []):
                    if isinstance(row, dict):
                        lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
                    elif isinstance(row, list):
                        lines.append("| " + " | ".join(str(val) for val in row) + " |")
                lines.append("")

    links = data.get("links", [])
    if links:
        lines.append("## Links\n")
        for lnk in links[:20]:
            lines.append(f"- [{lnk.get('text')}]({lnk.get('url')})")
        lines.append("")

    # Algerian .dz Details
    dz = data.get("dz_data")
    if dz:
        dns = dz.get("dns", {})
        has_dz = dz.get("is_dz_website") or dns.get("has_dz_dns")
        if has_dz or dz.get("algerian_phones") or dz.get("wilayas_detected"):
            lines.append("## Algerian (.dz) Website & DNS Details\n")
            lines.append(f"- **Has .dz DNS / Domain:** `{'YES' if dns.get('has_dz_dns') else 'NO'}`")
            lines.append(f"- **Hostname:** `{dns.get('hostname')}`")
            if dns.get("canonical_name"):
                lines.append(f"- **Canonical Name:** `{dns.get('canonical_name')}`")
            if dns.get("ip_addresses"):
                lines.append(f"- **IP Addresses:** {', '.join(dns.get('ip_addresses'))}")
            if dns.get("nameservers"):
                lines.append(f"- **Nameservers:** {', '.join(dns.get('nameservers'))}")
            if dz.get("algerian_phones"):
                lines.append(f"- **Algerian Phone Numbers:** {', '.join(dz.get('algerian_phones'))}")
            if dz.get("wilayas_detected"):
                lines.append(f"- **Wilayas Detected:** {', '.join(dz.get('wilayas_detected'))}")
            cids = dz.get("commercial_identifiers", {})
            if cids:
                lines.append("- **Commercial & Administrative Identifiers:**")
                for k, v in cids.items():
                    lines.append(f"  - **{k.upper()}**: `{v}`")
            dz_l = dz.get("discovered_dz_links", [])
            if dz_l:
                lines.append(f"- **Discovered .dz Links ({len(dz_l)} total):**")
                for dl in dz_l[:6]:
                    lines.append(f"  - [{dl.get('text')}]({dl.get('url')})")
            lines.append("")

    # Google Info
    g_info = data.get("google_info")
    if g_info:
        lines.append("## Google Information & Related URLs\n")
        lines.append(f"- **Google Search:** [{g_info.get('google_search_url')}]({g_info.get('google_search_url')})")
        lines.append(f"- **Google Site Search:** [{g_info.get('google_site_search_url')}]({g_info.get('google_site_search_url')})")
        lines.append(f"- **Google Web Cache:** [{g_info.get('google_cache_url')}]({g_info.get('google_cache_url')})\n")
        queries = g_info.get("google_related_queries", [])
        if queries:
            lines.append("### Google Related Queries\n")
            for q in queries[:6]:
                lines.append(f"- {q}")
            lines.append("")
        rel_urls = g_info.get("google_related_urls", [])
        if rel_urls:
            lines.append("### Google Discovered Related URLs\n")
            for u in rel_urls[:6]:
                lines.append(f"- [{u}]({u})")
            lines.append("")

    return "\n".join(lines)



def scrape_url(
    url: str,
    selector: Optional[str] = None,
    timeout: int = 15,
    use_stealth: bool = False,
    include_dz_data: bool = True,
    include_google_info: bool = False,
) -> Dict[str, Any]:
    """
    Convenience function to scrape a single URL with default settings.
    """
    scraper = WebScraper(timeout=timeout, use_stealth=use_stealth)
    return scraper.scrape(
        url,
        selector=selector,
        include_dz_data=include_dz_data,
        include_google_info=include_google_info,
    )


def crawl_website(
    url: str,
    max_pages: int = 10,
    selector: Optional[str] = None,
    timeout: int = 15,
    delay: float = 0.5,
    use_stealth: bool = False,
    include_dz_data: bool = True,
    include_google_info: bool = False,
) -> Dict[str, Any]:
    """
    Convenience function to automatically navigate through related pages of a website.
    Default navigates through up to 10 pages.
    """
    scraper = WebScraper(timeout=timeout, use_stealth=use_stealth)
    return scraper.crawl(
        url,
        max_pages=max_pages,
        selector=selector,
        delay=delay,
        include_dz_data=include_dz_data,
        include_google_info=include_google_info,
    )


def fetch_google_info(domain_or_url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """
    Convenience function to return Google infos and URLs related to the website.
    """
    return get_google_info(domain_or_url, timeout=timeout)


def main() -> None:
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description="Scrape small amounts of structured data from a given URL with .dz DNS analysis, automatic multi-page navigation, and Google information extraction.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py https://example.com
  python scraper.py algerietelecom.dz --format json
  python scraper.py algerietelecom.dz --crawl --max-pages 10
  python scraper.py algerietelecom.dz --google-info
  python scraper.py elmoudjahid.dz --dz-only --crawl --google-info
  python scraper.py https://example.com --selector "h1, p"
  python scraper.py https://example.com --stealth --format markdown -o report.md
        """,
    )

    parser.add_argument("url", help="Target URL to scrape or crawl (e.g. https://example.com)")
    parser.add_argument(
        "-s",
        "--selector",
        help="CSS or XPath selector to extract specific elements (e.g. '.product-title', '//h1')",
        default=None,
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output display format (default: text)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional file path to save output (e.g. output.json or output.md)",
        default=None,
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=15,
        help="HTTP request timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--stealth",
        action="store_true",
        help="Use Scrapling stealth fetcher to bypass basic bot protections and TLS fingerprinting",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable SSL certificate verification (use with caution)",
    )
    parser.add_argument(
        "-c",
        "--crawl",
        action="store_true",
        help="Enable automatic navigation through up to 10 related pages of the URL",
    )
    parser.add_argument(
        "-m",
        "--max-pages",
        type=int,
        default=10,
        help="Maximum number of related pages to automatically navigate (default: 10)",
    )
    parser.add_argument(
        "--crawl-delay",
        type=float,
        default=0.5,
        help="Delay in seconds between page requests during crawling (default: 0.5)",
    )
    parser.add_argument(
        "-g",
        "--google-info",
        action="store_true",
        help="Fetch Google search information and related URLs for the target website",
    )
    parser.add_argument(
        "--dz-only",
        action="store_true",
        help="Verify that the target website has .dz domain or .dz DNS before scraping",
    )

    args = parser.parse_args()

    try:
        if args.dz_only:
            dns_chk = get_dz_dns_info(args.url, timeout=5.0)
            if not dns_chk.get("has_dz_dns"):
                print(
                    f"Error: Target '{args.url}' does not have verified .dz domain or .dz DNS records.",
                    file=sys.stderr,
                )
                sys.exit(1)

        scraper = WebScraper(
            timeout=args.timeout,
            verify_ssl=not args.no_verify_ssl,
            use_stealth=args.stealth,
        )

        if args.crawl:
            data = scraper.crawl(
                args.url,
                max_pages=args.max_pages,
                selector=args.selector,
                delay=args.crawl_delay,
                include_dz_data=True,
                include_google_info=args.google_info,
            )
        else:
            data = scraper.scrape(
                args.url,
                selector=args.selector,
                include_dz_data=True,
                include_google_info=args.google_info,
            )

        # Format output
        if args.format == "json":
            rendered = json.dumps(data, indent=2, ensure_ascii=False)
        elif args.format == "markdown":
            rendered = format_as_markdown(data)
        else:
            rendered = format_as_text(data)

        # Output to console or file
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(rendered)
            print(f"Scraped data successfully saved to: {args.output}")
        else:
            print(rendered)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL '{args.url}': {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error while scraping: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

