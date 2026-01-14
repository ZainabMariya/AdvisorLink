import os
import re
import json
import asyncio
import hashlib
import sqlite3
import traceback
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, urldefrag, urljoin
from xml.etree import ElementTree

import requests
import certifi
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from lxml import etree
import urllib3

from openai import AsyncOpenAI
from pinecone import Pinecone, ServerlessSpec

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# =========================
# Config
# =========================
SITEMAP_URL = "https://psu.edu.sa/sitemap.xml"
# If you keep hitting SSL issues, try:
# SITEMAP_URL = "https://www.psu.edu.sa/sitemap.xml"

INDEX_NAME = "psu-web-auto"

# OpenAI embedding model configuration - requests native 3072 dimensions
# Matches the Pinecone index dimension for vector storage
EMBED_MODEL = "text-embedding-3-large"
EMBED_DIMENSION = 3072

USER_AGENT = "PSU-KB-Crawler/2.0"
# Store database in same directory as crawler script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "crawl_state.db")

# Concurrency / batching
MAX_CONCURRENT_FETCH = 20
MAX_CONCURRENT_EMBED = 5
UPSERT_BATCH_SIZE = 100
EMBED_BATCH_SIZE = 64

# Chunking
CHUNK_MAX_CHARS = 3500
CHUNK_OVERLAP_CHARS = 200
MIN_CHUNK_CHARS = 250

# URL filtering
BLOCKED_SUBSTRINGS = [
    "/ar/", "/news/", "/blog/", "/post/", "/article/", "news-item", "/events/"
]

# Main-content selection
MAIN_SELECTORS = ["main", "article", "#content", ".entry-content", ".page-content", ".content", ".entry"]
REMOVE_SELECTORS = [
    "header", "nav", "footer", "aside",
    ".navbar", ".menu", ".site-header", ".site-footer",
    ".cookie", ".cookies", ".popup", ".modal",
    ".breadcrumb", ".breadcrumbs",
]

# =========================
# Env & clients
# =========================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

if not OPENAI_API_KEY or not PINECONE_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY and/or PINECONE_API_KEY in environment variables.")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)

# =========================
# Pinecone vector database initialization
# =========================
# Creates or validates Pinecone index with correct dimensions and metric
# Uses cosine similarity for semantic search relevance
def init_pinecone_index():
    existing = [i.name for i in pc.list_indexes()]

    if INDEX_NAME in existing:
        idx_info = pc.describe_index(INDEX_NAME)
        if idx_info.dimension != EMBED_DIMENSION:
            print(f"Index {INDEX_NAME} has wrong dimension ({idx_info.dimension}). Deleting and recreating...")
            pc.delete_index(INDEX_NAME)
            pc.create_index(
                name=INDEX_NAME,
                dimension=EMBED_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            print(f"Created Pinecone index: {INDEX_NAME} with correct dimensions ({EMBED_DIMENSION})")
        else:
            print(f"Using existing Pinecone index: {INDEX_NAME}")
    else:
        pc.create_index(
            name=INDEX_NAME,
            dimension=EMBED_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        print(f"Created Pinecone index: {INDEX_NAME} with {EMBED_DIMENSION} dimensions")

    return pc.Index(INDEX_NAME)

index = init_pinecone_index()

# =========================
# SQLite crawl state tracking
# =========================
# Database tracks previously crawled URLs and their metadata to enable incremental updates
# Stores ETag, Last-Modified headers, and content hash to detect changes
def init_db():
    """Initialize SQLite database. Creates it if it doesn't exist, overwrites table if needed."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            url TEXT PRIMARY KEY,
            sitemap_lastmod TEXT,
            etag TEXT,
            last_modified TEXT,
            content_hash TEXT,
            last_crawled_at TEXT
        )
        """)
        conn.commit()
        conn.close()
        logger.info(f"Database ready at {DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

def get_state(url: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached metadata for a URL (etag, last_modified, content_hash, etc.)"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT sitemap_lastmod, etag, last_modified, content_hash FROM pages WHERE url=?", (url,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "sitemap_lastmod": row[0],
        "etag": row[1],
        "last_modified": row[2],
        "content_hash": row[3],
    }

def upsert_state(url: str,
                 sitemap_lastmod: Optional[str],
                 etag: Optional[str],
                 last_modified: Optional[str],
                 content_hash: Optional[str]):
    """Update crawl state for a URL with HTTP headers and content metadata"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO pages(url, sitemap_lastmod, etag, last_modified, content_hash, last_crawled_at)
    VALUES(?,?,?,?,?,?)
    ON CONFLICT(url) DO UPDATE SET
        sitemap_lastmod=excluded.sitemap_lastmod,
        etag=excluded.etag,
        last_modified=excluded.last_modified,
        content_hash=excluded.content_hash,
        last_crawled_at=excluded.last_crawled_at
    """, (
        url, sitemap_lastmod, etag, last_modified, content_hash,
        datetime.now(timezone.utc).isoformat()
    ))
    conn.commit()
    conn.close()

# =========================
# Helper functions
# =========================
# Utility functions for URL normalization, text cleaning, and content hashing
def sha256_text(s: str) -> str:
    """Generate SHA-256 hash of text content to detect changes.
    
    Used to identify when page content has been modified since last crawl.
    """
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

def normalize_url(url: str) -> Optional[str]:
    """Normalize and validate URLs for crawling.
    
    Removes fragments, validates scheme, and filters blocked substrings.
    Returns None for invalid or blocked URLs.
    """
    if not url:
        return None
    url = url.strip().split()[0]
    url, _ = urldefrag(url)
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return None
    low = url.lower()
    if any(b in low for b in BLOCKED_SUBSTRINGS):
        return None
    return url

def clean_whitespace(s: str) -> str:
    """Normalize whitespace in text by removing carriage returns and excess newlines.
    
    Consolidates multiple consecutive newlines into single double newlines.
    """
    s = re.sub(r"\r", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()

# =========================
# Sitemap parsing
# =========================
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

def fetch_xml(url: str):
    try:
        ca_bundle = certifi.where()
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120, verify=ca_bundle)
        r.raise_for_status()
    except requests.exceptions.SSLError:
        logger.warning(f"SSL verification failed for {url}, retrying without verification")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120, verify=False)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return etree.Element("urlset")

    try:
        parser = etree.XMLParser(recover=True)
        return etree.fromstring(r.content, parser=parser)
    except Exception as e:
        logger.error(f"XML parsing error at {url}: {e}")
        return etree.Element("urlset")

def parse_sitemap(url: str) -> List[Tuple[str, Optional[str]]]:
    root = fetch_xml(url)
    tag = root.tag.lower()

    if tag.endswith("sitemapindex"):
        all_entries: List[Tuple[str, Optional[str]]] = []
        for sm in root.findall("sm:sitemap", NS):
            loc_el = sm.find("sm:loc", NS)
            if loc_el is None or not loc_el.text:
                continue
            all_entries.extend(parse_sitemap(loc_el.text.strip()))
        return all_entries

    entries: List[Tuple[str, Optional[str]]] = []
    for u in root.findall("sm:url", NS):
        loc_el = u.find("sm:loc", NS)
        if loc_el is None or not loc_el.text:
            continue
        loc = normalize_url(loc_el.text)
        if not loc:
            continue
        lastmod_el = u.find("sm:lastmod", NS)
        lastmod = lastmod_el.text.strip() if (lastmod_el is not None and lastmod_el.text) else None
        entries.append((loc, lastmod))
    return entries

# =========================
# Fetch pages
# =========================
def fetch_page(url: str, state: Optional[Dict[str, Any]]) -> Tuple[Optional[str], Dict[str, Any]]:
    headers = {"User-Agent": USER_AGENT}
    if state:
        if state.get("etag"):
            headers["If-None-Match"] = state["etag"]
        if state.get("last_modified"):
            headers["If-Modified-Since"] = state["last_modified"]

    try:
        ca_bundle = certifi.where()
        r = requests.get(url, headers=headers, timeout=80, allow_redirects=True, verify=ca_bundle)
    except requests.exceptions.SSLError:
        logger.warning(f"SSL verification failed for {url}, retrying without verification")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        r = requests.get(url, headers=headers, timeout=80, allow_redirects=True, verify=False)
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching {url}")
        return None, {"status": 0, "final_url": url}
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {e}")
        return None, {"status": 0, "final_url": url}

    meta = {
        "status": r.status_code,
        "final_url": r.url,
        "etag": r.headers.get("ETag"),
        "last_modified": r.headers.get("Last-Modified"),
        "content_type": r.headers.get("Content-Type", ""),
    }

    if r.status_code == 304:
        return None, meta
    if r.status_code != 200:
        logger.warning(f"Non-200 status for {url}: {r.status_code}")
        return None, meta

    return r.text, meta

# =========================
# Extraction
# =========================
def extract_page_metadata(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1_el = soup.find("h1")
    h1 = h1_el.get_text(" ", strip=True) if h1_el else ""

    canonical_el = soup.select_one('link[rel="canonical"]')
    canonical_url = canonical_el.get("href", "").strip() if canonical_el else ""
    canonical_url = urljoin(url, canonical_url) if canonical_url else url

    downloads = []
    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        full = urljoin(url, href)
        if full.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")):
            downloads.append(full)
    downloads = list(dict.fromkeys(downloads))[:50]

    return {"page_title": title, "h1": h1, "canonical_url": canonical_url, "download_links": downloads}

def pick_main_container(soup: BeautifulSoup) -> Tuple[BeautifulSoup, bool]:
    for sel in REMOVE_SELECTORS:
        for node in soup.select(sel):
            node.decompose()

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    for sel in MAIN_SELECTORS:
        node = soup.select_one(sel)
        if node and node.get_text(strip=True):
            return node, True

    return soup.body or soup, False

def html_to_structured_text(container: BeautifulSoup) -> str:
    lines: List[str] = []
    for el in container.find_all(["h1","h2","h3","h4","h5","h6","p","li","table"]):
        name = el.name.lower()
        if name.startswith("h"):
            level = int(name[1])
            txt = el.get_text(" ", strip=True)
            if txt:
                lines.append(f"{'#'*level} {txt}")
        elif name == "p":
            txt = el.get_text(" ", strip=True)
            if txt:
                lines.append(txt)
        elif name == "li":
            txt = el.get_text(" ", strip=True)
            if txt:
                lines.append(f"- {txt}")
        elif name == "table":
            for row in el.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in row.find_all(["th","td"])]
                cells = [c for c in cells if c]
                if cells:
                    lines.append(" | ".join(cells))

    return clean_whitespace("\n".join(lines))

# =========================
# Chunking
# =========================
def split_by_headings(text: str) -> List[Tuple[str, str]]:
    lines = text.splitlines()
    sections: List[Tuple[str, List[str]]] = []
    current_heading = "Introduction"
    current: List[str] = []
    heading_re = re.compile(r"^(#{1,6})\s+(.*)$")

    for line in lines:
        m = heading_re.match(line.strip())
        if m:
            if current:
                sections.append((current_heading, current))
            current_heading = m.group(2).strip() or "Untitled"
            current = []
        else:
            if line.strip():
                current.append(line)

    if current:
        sections.append((current_heading, current))

    return [(h, clean_whitespace("\n".join(body))) for h, body in sections if body]

# Text chunking strategy - splits documents into overlapping chunks to preserve context
# Respects word boundaries to avoid splitting mid-word
def chunk_section_text(section_text: str, max_chars: int = CHUNK_MAX_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> List[str]:
    s = section_text.strip()
    if not s:
        return []
    chunks = []
    start = 0
    n = len(s)

    while start < n:
        end = min(start + max_chars, n)
        window = s[start:end]
        last_break = window.rfind("\n\n")
        if last_break > max_chars * 0.5:
            end = start + last_break

        chunk = s[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= n:
            break
        start = max(0, end - overlap)

    return chunks

def chunk_document(structured_text: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for heading, body in split_by_headings(structured_text):
        if len(body) < MIN_CHUNK_CHARS:
            continue
        for p in chunk_section_text(body):
            if len(p) >= MIN_CHUNK_CHARS:
                out.append((heading, p))
    return out

# =========================
# Embeddings and Pinecone upsert
# =========================
# Data structure representing a vector record for Pinecone
# Contains embedding vector, chunk metadata, and source information
@dataclass
class VectorRecord:
    id: str
    values: List[float]
    metadata: Dict[str, Any]

def make_chunk_id(url: str, chunk_index: int) -> str:
    """Generate a unique identifier for a chunk by combining URL and chunk index.
    
    Sanitizes URL by replacing special characters to create valid Pinecone record ID.
    """
    safe = url.replace("://", "_").replace("/", "_")
    return f"{safe}_{chunk_index}"

# Request native 3072 embeddings from OpenAI
# This directly creates embeddings at the target dimension without padding or truncation
async def embed_texts(texts: List[str]) -> List[List[float]]:
    resp = await openai_client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
        dimensions=EMBED_DIMENSION,
    )
    return [d.embedding for d in resp.data]

def looks_incomplete(structured_text: str) -> bool:
    """Check if extracted content appears incomplete or too minimal.
    
    Uses word count threshold to detect pages where extraction may have failed.
    """
    return len(re.findall(r"\w+", structured_text)) < 10

async def process_url(url: str, sitemap_lastmod: Optional[str], fetch_sem: asyncio.Semaphore, embed_sem: asyncio.Semaphore) -> Dict[str, Any]:
    """Process a single URL: fetch, extract content, chunk, embed, and upsert to Pinecone.
    
    Uses semaphores to control concurrent fetch and embedding operations.
    Checks cache using ETag and content hash to avoid reprocessing unchanged content.
    Returns status dict indicating if URL was updated, skipped, or failed with reason.
    """
    """Process a single URL: fetch, extract content, chunk, embed, and upsert to Pinecone
    
    Uses semaphores to control concurrent fetch and embedding operations.
    Returns status indicating if URL was updated, skipped, or failed.
    """
    state = get_state(url)

    if state and sitemap_lastmod and state.get("sitemap_lastmod"):
        try:
            if sitemap_lastmod <= state["sitemap_lastmod"]:
                return {"url": url, "skipped": True, "reason": "sitemap_lastmod_unchanged"}
        except:
            pass

    async with fetch_sem:
        html, meta = await asyncio.to_thread(fetch_page, url, state)

    if meta.get("status") == 304:
        upsert_state(url, sitemap_lastmod, state.get("etag") if state else None,
                     state.get("last_modified") if state else None,
                     state.get("content_hash") if state else None)
        return {"url": url, "skipped": True, "reason": "http_304"}

    if html is None:
        return {"url": url, "skipped": True, "reason": f"http_{meta.get('status')}"}

    soup = BeautifulSoup(html, "html.parser")
    page_meta = extract_page_metadata(soup, url)
    container, _ = pick_main_container(soup)
    structured = html_to_structured_text(container)

    if looks_incomplete(structured):
        upsert_state(url, sitemap_lastmod, meta.get("etag"), meta.get("last_modified"),
                     state.get("content_hash") if state else None)
        return {"url": url, "skipped": True, "reason": "incomplete_extraction"}

    content_hash = sha256_text(structured)
    if state and state.get("content_hash") == content_hash:
        upsert_state(url, sitemap_lastmod, meta.get("etag"), meta.get("last_modified"), content_hash)
        return {"url": url, "skipped": True, "reason": "hash_unchanged"}

    chunk_pairs = chunk_document(structured)
    if not chunk_pairs:
        upsert_state(url, sitemap_lastmod, meta.get("etag"), meta.get("last_modified"), content_hash)
        return {"url": url, "skipped": True, "reason": "no_chunks"}

    texts, headings = [], []
    for heading, chunk_text in chunk_pairs:
        texts.append(f"Section: {heading}\n\n{chunk_text}")
        headings.append(heading)

    embeddings: List[List[float]] = []
    async with embed_sem:
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            embeddings.extend(await embed_texts(texts[i:i + EMBED_BATCH_SIZE]))

    crawled_at = datetime.now(timezone.utc).isoformat()
    domain = urlparse(url).netloc
    path = urlparse(url).path

    records: List[VectorRecord] = []
    for i, (vec, heading, combined_text) in enumerate(zip(embeddings, headings, texts)):
        md = {
            "url": url,
            "canonical_url": page_meta.get("canonical_url", url),
            "page_title": page_meta.get("page_title", ""),
            "h1": page_meta.get("h1", ""),
            "section_heading": heading,
            "source": domain,
            "url_path": path,
            "chunk_index": i,
            "total_chunks": len(texts),
            "content_type": "text/structured",
            "crawled_at": crawled_at,
            "sitemap_lastmod": sitemap_lastmod,
            "http_status": meta.get("status"),
            "final_url": meta.get("final_url", url),
            "etag": meta.get("etag"),
            "last_modified": meta.get("last_modified"),
            "content_hash": content_hash,
            "text": combined_text[:8000],
            "download_links": page_meta.get("download_links", []),
        }
        md = {k: v for k, v in md.items() if v is not None}
        records.append(VectorRecord(id=make_chunk_id(url, i), values=vec, metadata=md))

    try:
        for i in range(0, len(records), UPSERT_BATCH_SIZE):
            batch = records[i:i + UPSERT_BATCH_SIZE]
            vectors = [{"id": r.id, "values": r.values, "metadata": r.metadata} for r in batch]
            logger.info(f"Upserting {len(vectors)} vectors for {url}")
            await asyncio.wait_for(asyncio.to_thread(index.upsert, vectors=vectors), timeout=60.0)
    except asyncio.TimeoutError:
        return {"url": url, "error": "pinecone_upsert_timeout"}
    except Exception as e:
        return {"url": url, "error": f"pinecone_upsert_failed: {e}"}

    upsert_state(url, sitemap_lastmod, meta.get("etag"), meta.get("last_modified"), content_hash)
    return {"url": url, "updated": True, "chunks": len(records)}

# =========================
# Main crawling orchestration
# =========================
# Orchestrates the entire crawl process:
# 1. Initialize database for crawl state tracking
# 2. Load and parse sitemap from PSU website
# 3. Create worker pool for concurrent URL processing
# 4. Process each URL with concurrent fetch and embedding
# 5. Generate crawl report with statistics
async def run():
    init_db()
    print(f"Loading sitemap: {SITEMAP_URL}")
    entries = parse_sitemap(SITEMAP_URL)
    print(f"Found {len(entries)} URLs from sitemap")

    fetch_sem = asyncio.Semaphore(MAX_CONCURRENT_FETCH)
    embed_sem = asyncio.Semaphore(MAX_CONCURRENT_EMBED)

    q: asyncio.Queue[Tuple[str, Optional[str]]] = asyncio.Queue()
    for url, lastmod in entries:
        q.put_nowait((url, lastmod))

    stats = {"updated": 0, "skipped": 0, "errors": 0, "reasons": {}}
    failed: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    async def worker(worker_id: int):
        nonlocal stats, failed, skipped
        while True:
            try:
                url, lastmod = q.get_nowait()
            except asyncio.QueueEmpty:
                return

            try:
                r = await process_url(url, lastmod, fetch_sem, embed_sem)
                if r.get("error"):
                    stats["errors"] += 1
                    failed.append({"url": url, "error": r["error"]})
                    print(f"[ERR] {url} -> {r['error']}", flush=True)
                elif r.get("updated"):
                    stats["updated"] += 1
                    print(f"[UPD] {url} -> {r.get('chunks', 0)} chunks", flush=True)
                else:
                    stats["skipped"] += 1
                    reason = r.get("reason", "skipped")
                    stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1
                    skipped.append({"url": url, "reason": reason})
                    print(f"[SKP] {url} -> {reason}", flush=True)
            except Exception as e:
                stats["errors"] += 1
                failed.append({"url": url, "error": str(e)})
                print(f"[ERR] {url} -> {e}", flush=True)
                traceback.print_exc()
            finally:
                q.task_done()

    workers = [asyncio.create_task(worker(i)) for i in range(12)]
    await asyncio.gather(*workers)

    report = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "sitemap_url_count": len(entries),
        "stats": stats,
        "failed": failed,
        "skipped": skipped,
    }

    # Save report, overwriting if it exists or creating if it doesn't
    report_path = os.path.join(SCRIPT_DIR, "crawl_report.json")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"Crawl report saved to {report_path}")
    except Exception as e:
        logger.error(f"Failed to save crawl report: {e}")

    print("Done.")
    print(json.dumps(report["stats"], indent=2))
    if failed:
        print(f"Failed URLs: {len(failed)} (see crawl_report.json)")
    if skipped:
        print(f"Skipped URLs: {len(skipped)} (see crawl_report.json)")

if __name__ == "__main__":
    asyncio.run(run())
