"""
backfill_tps.py — Scrape ALL historical TPS press releases using headful Playwright.

tps.ca is behind Cloudflare bot protection. Headful mode (real browser window)
bypasses this naturally.

Run with:
    uv run python backfill_tps.py

The script is resumable — it skips URLs already in data/archive/toronto-police-service.json.
Progress is checkpointed every 20 articles.
"""

import hashlib
import json
import re
import time
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout

from scan import normalize_date, clean_content

# --- Config ---

BASE_DIR = Path(__file__).parent
ARCHIVE_DIR = BASE_DIR / "data" / "archive"
ARCHIVE_FILE = ARCHIVE_DIR / "toronto-police-service.json"

SERVICE_NAME = "Toronto Police Service"
LISTING_URL = "https://www.tps.ca/media-centre/news-releases/"

PAGE_DELAY = 2.5       # seconds between page navigations
ARTICLE_DELAY = 2.0    # seconds between article fetches
CHECKPOINT_EVERY = 20  # save to disk after this many new articles
MAX_PAGES = 500        # safety cap on listing pages


# --- Storage ---

def item_hash(title: str, url: str) -> str:
    return hashlib.md5((title.strip() + "|" + url.strip()).encode()).hexdigest()


def load_archive() -> list[dict]:
    if ARCHIVE_FILE.exists():
        try:
            return json.loads(ARCHIVE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_archive(items: list[dict]) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --- Link extraction from listing pages ---

_TPS_RELEASE_RE = re.compile(r"/media-centre/news-releases/\d+/$")


def _is_real_release_url(href: str) -> bool:
    """True for numeric-ID release URLs like /media-centre/news-releases/66184/.
    Rejects division links (/my-neighbourhood/), storyline anchors (#storyline),
    and slug-only URLs that are duplicates of the numeric versions.
    """
    if "#" in href:
        return False
    if "/my-neighbourhood/" in href:
        return False
    return bool(_TPS_RELEASE_RE.search(href))


def extract_listing_items(page: Page, base_url: str) -> list[dict]:
    """Return [{title, url, date}] from a TPS listing page."""
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    results = []
    seen_urls: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href.startswith("http"):
            href = "https://www.tps.ca" + href if href.startswith("/") else base_url.rstrip("/") + "/" + href

        if not _is_real_release_url(href):
            continue
        if href in seen_urls:
            continue
        if a.find_parent(["nav", "header", "footer"]):
            continue
        seen_urls.add(href)

        # Title: prefer text on the anchor; if it's just whitespace try parent heading
        title = a.get_text(separator=" ", strip=True)
        if not title or len(title) < 5:
            heading = a.find_parent(["h2", "h3", "h4"])
            if heading:
                title = heading.get_text(separator=" ", strip=True)
        if not title:
            continue

        # Hunt for a date in the surrounding markup (up to 5 parent levels)
        date_str = None
        node = a.parent
        for _ in range(5):
            if node is None:
                break
            t = node.find("time")
            if t:
                date_str = t.get("datetime", "") or t.get_text(strip=True)
                break
            text = node.get_text(separator=" ", strip=True)
            m = re.search(
                r"\b(January|February|March|April|May|June|July|August"
                r"|September|October|November|December)\s+\d{1,2},?\s*\d{4}\b",
                text,
            )
            if m:
                date_str = m.group(0)
                break
            node = node.parent

        results.append({"title": title, "url": href, "date": date_str})

    return results


# --- Pagination ---

def find_next_page(page: Page, current_url: str) -> str | None:
    """Return the URL of the next listing page, or None if on last page."""
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    # 1. <link rel="next"> in <head>
    link = soup.find("link", rel="next")
    if link and link.get("href"):
        href = link["href"]
        return href if href.startswith("http") else "https://www.tps.ca" + href

    # 2. <a rel="next">
    a = soup.find("a", rel="next")
    if a and a.get("href"):
        href = a["href"]
        return href if href.startswith("http") else "https://www.tps.ca" + href

    # 3. aria-label="Next page" / aria-label="Next"
    a = soup.find("a", attrs={"aria-label": re.compile(r"next", re.IGNORECASE)})
    if a and a.get("href") and not a["href"].startswith("#"):
        href = a["href"]
        return href if href.startswith("http") else "https://www.tps.ca" + href

    # 4. Link text: "Next", "›", "»", ">"
    for pat in [
        re.compile(r"^\s*(Next|›|»|>)\s*$", re.IGNORECASE),
        re.compile(r"next\s+page", re.IGNORECASE),
        re.compile(r"older\s+posts", re.IGNORECASE),
    ]:
        a = soup.find("a", string=pat)
        if a and a.get("href") and not a["href"].startswith("#"):
            href = a["href"]
            return href if href.startswith("http") else "https://www.tps.ca" + href

    # 5. CSS class patterns
    for sel in [
        "a.next-btn",           # TPS-specific
        "a.next", ".pagination a.next", ".pager-next a",
        "li.next a", ".wp-pagenavi a.nextpostslink",
        "nav.pagination a[rel='next']",
    ]:
        a = soup.select_one(sel)
        if a and a.get("href") and not a["href"].startswith("#"):
            href = a["href"]
            return href if href.startswith("http") else "https://www.tps.ca" + href

    return None


# --- Article content extraction ---

def extract_article(page: Page, title: str) -> tuple[str | None, str | None]:
    """
    Return (content, date_str) from an open TPS article page.
    date_str may be None if not found on the page.
    """
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    # Remove boilerplate tags before extracting text
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "form", "noscript", "aside"]):
        tag.decompose()

    # Date: prefer <time datetime="..."> or <meta> tags
    date_str = None
    time_el = soup.find("time")
    if time_el:
        date_str = time_el.get("datetime", "") or time_el.get_text(strip=True)
    if not date_str:
        for meta_attr in [
            {"property": "article:published_time"},
            {"name": "date"},
            {"name": "pubdate"},
        ]:
            meta = soup.find("meta", meta_attr)
            if meta:
                date_str = (meta.get("content") or "")[:10]
                break
    if not date_str:
        # Search visible text for a month-name date
        body_text = soup.get_text(separator=" ", strip=True)
        m = re.search(
            r"\b(January|February|March|April|May|June|July|August"
            r"|September|October|November|December)\s+\d{1,2},?\s*\d{4}\b",
            body_text,
        )
        if m:
            date_str = m.group(0)

    # Content: work down from most-specific to broadest container
    content = None
    for sel in [
        "article",
        "main",
        ".entry-content",
        ".post-content",
        ".article-body",
        ".content-body",
        ".news-body",
        ".field--name-body",
        "#content",
        ".content",
        "div[class*='content']",
        "body",
    ]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 100:
                text = re.sub(r"\n{3,}", "\n\n", text)
                content = clean_content(text.strip(), title)
                break

    return content, date_str


# --- Main ---

def main() -> None:
    today_iso = date.today().isoformat()

    existing = load_archive()
    seen_urls: set[str] = {item["url"] for item in existing if item.get("url")}
    seen_hashes: set[str] = {item["item_hash"] for item in existing if item.get("item_hash")}
    print(f"Existing archive: {len(existing)} items, {len(seen_urls)} unique URLs")

    new_items: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=50,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        pw_page = context.new_page()

        # ── Phase 1: Walk listing pages, collect all links ──────────────────

        all_links: list[dict] = []
        current_url: str | None = LISTING_URL
        page_num = 0

        print("\nPhase 1: Collecting listing pages…")
        while current_url and page_num < MAX_PAGES:
            page_num += 1
            print(f"  Page {page_num}: {current_url}")
            try:
                pw_page.goto(current_url, wait_until="networkidle", timeout=45000)
                time.sleep(PAGE_DELAY)
            except PlaywrightTimeout:
                print("    Timeout — waiting an extra 5 s then continuing…")
                time.sleep(5)

            # Scroll to the bottom repeatedly to trigger infinite-scroll / lazy-load
            prev_height = 0
            for _ in range(8):
                pw_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.2)
                height = pw_page.evaluate("document.body.scrollHeight")
                if height == prev_height:
                    break
                prev_height = height

            seen_in_links = {x["url"] for x in all_links}
            items = extract_listing_items(pw_page, current_url)
            new_on_page = [i for i in items if i["url"] not in seen_urls
                           and i["url"] not in seen_in_links]
            print(f"    {len(items)} links found, {len(new_on_page)} new")
            all_links.extend(new_on_page)

            # If every link on this page is already known, stop paginating.
            if items and not new_on_page:
                print("    All links on this page already archived — stopping pagination.")
                break

            next_url = find_next_page(pw_page, current_url)
            if not next_url or next_url == current_url:
                # Try common WordPress-style page increment as fallback
                from urllib.parse import urlparse, urlunparse, urlencode, parse_qs
                parsed = urlparse(current_url)
                qs = parse_qs(parsed.query)
                pg = int(qs.get("page", ["1"])[0])
                candidate = urlunparse(parsed._replace(
                    query=urlencode({**{k: v[0] for k, v in qs.items()}, "page": pg + 1})
                ))
                # Also try /page/N/ (WordPress permalink style)
                wp_candidate = LISTING_URL.rstrip("/") + f"/page/{page_num + 1}/"
                # Quick check: try the page increment; if we get no new items, stop.
                try:
                    pw_page.goto(wp_candidate, wait_until="networkidle", timeout=20000)
                    time.sleep(1)
                    wp_items = extract_listing_items(pw_page, wp_candidate)
                    wp_new = [i for i in wp_items if i["url"] not in seen_urls
                              and i["url"] not in {x["url"] for x in all_links}]
                    if wp_new:
                        print(f"    WordPress /page/{page_num + 1}/ has {len(wp_new)} new items — using it")
                        current_url = wp_candidate
                        all_links.extend(wp_new)
                        continue
                except Exception:
                    pass
                print("  No next-page link found — reached end of listing.")
                break
            current_url = next_url

        print(f"\nTotal new links to scrape: {len(all_links)}")

        # ── Phase 2: Fetch content for each new article ──────────────────────

        print("\nPhase 2: Scraping articles…")
        for i, link in enumerate(all_links, start=1):
            url = link["url"]
            title = link["title"]
            list_date = link.get("date")

            h = item_hash(title, url)
            if h in seen_hashes:
                print(f"  [{i}/{len(all_links)}] Skipping (already hashed): {title[:60]}")
                continue

            print(f"  [{i}/{len(all_links)}] {title[:70]}")

            content = None
            article_date = list_date
            try:
                pw_page.goto(url, wait_until="networkidle", timeout=45000)
                time.sleep(ARTICLE_DELAY)
                content, page_date = extract_article(pw_page, title)
                if page_date and not article_date:
                    article_date = page_date
            except PlaywrightTimeout:
                print(f"    Timeout on article, skipping content.")
            except Exception as exc:
                print(f"    Error: {exc}")

            iso_date = normalize_date(article_date)
            record = {
                "item_hash": h,
                "title": title,
                "url": url,
                "date": iso_date,
                "service_name": SERVICE_NAME,
                "content": content,
                "first_scraped_at": today_iso,
            }
            new_items.append(record)
            seen_hashes.add(h)
            seen_urls.add(url)

            # Checkpoint save
            if len(new_items) % CHECKPOINT_EVERY == 0:
                merged = existing + new_items
                save_archive(merged)
                print(f"    [checkpoint] {len(merged)} total items saved")

        browser.close()

    # Final save
    merged = existing + new_items
    save_archive(merged)
    print(f"\nDone. Added {len(new_items)} new items. Total archive: {len(merged)}")


if __name__ == "__main__":
    main()
