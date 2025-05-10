import os
import json
import asyncio
import requests
from xml.etree import ElementTree
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from urllib.parse import urlparse
from dotenv import load_dotenv
import traceback

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from openai import AsyncOpenAI
from pinecone import Pinecone, ServerlessSpec
from chromadb.utils import embedding_functions

# Load API keys from .env
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
pinecone_api_key = os.getenv("PINECONE_API_KEY")
pinecone_environment = os.getenv("PINECONE_ENVIRONMENT")

if not all([openai_api_key, pinecone_api_key, pinecone_environment]):
    raise ValueError("Missing required environment variables: OPENAI_API_KEY, PINECONE_API_KEY, and/or PINECONE_ENVIRONMENT")

model_name = "gpt-4o-mini"

# Initialize OpenAI client and embedding function
openai_client = AsyncOpenAI(api_key=openai_api_key)
openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=openai_api_key,
    model_name="text-embedding-3-small"
)

# Initialize Pinecone
pc = Pinecone(api_key=pinecone_api_key)
index_name = "psu-website"

# Create index if not exists (manually setting dimension = 1536)
try:
    indexes = [i.name for i in pc.list_indexes()]
    if index_name not in indexes:
        pc.create_index(
            name=index_name,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        print(f"Created index: {index_name}")
    else:
        print(f"Using existing index: {index_name}")
    
    index = pc.Index(index_name)
except Exception as e:
    print(f"Error initializing Pinecone: {e}")
    traceback.print_exc()
    exit(1)

# Crawler configuration
browser_config = BrowserConfig(headless=True)
crawler_config = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    page_timeout=200_000,
    wait_until="domcontentloaded"
)
crawler = AsyncWebCrawler(config=browser_config)
failed_urls = []

@dataclass
class ProcessedChunk:
    url: str
    chunk_number: int
    title: str
    summary: str
    content: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None

def chunk_text(text: str, chunk_size: int = 5000) -> List[str]:
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + chunk_size
        if end >= text_length:
            chunks.append(text[start:].strip())
            break
        chunk = text[start:end]
        code_block = chunk.rfind('```')
        if code_block != -1 and code_block > chunk_size * 0.3:
            end = start + code_block
        elif '\n\n' in chunk:
            last_break = chunk.rfind('\n\n')
            if last_break > chunk_size * 0.3:
                end = start + last_break
        elif '. ' in chunk:
            last_period = chunk.rfind('. ')
            if last_period > chunk_size * 0.3:
                end = start + last_period + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = max(start + 1, end)
    return chunks

async def get_title_and_summary(chunk: str, url: str) -> Dict[str, str]:
    system_prompt = """You are an AI that extracts titles and summaries from website content chunks.
Return a JSON object with 'title' and 'summary' keys.
For the title: If this seems like the start of a document, extract its title. If it's a middle chunk, derive a descriptive title.
For the summary: Create a concise summary of the main points in this chunk.
Keep both title and summary concise but informative."""
    
    user_content = f"URL: {url}\n\nContent:\n{chunk[:1500]}..."

    try:
        response = await openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error getting title and summary for {url}: {e}")
        return {"title": f"Content from {urlparse(url).path}", "summary": "Content summary unavailable"}

async def insert_chunk(chunk: ProcessedChunk):
    try:
        if not chunk.embedding:
            response = await openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=chunk.content
            )
            chunk.embedding = response.data[0].embedding
        chunk_id = f"{chunk.url.replace('://', '_').replace('/', '_')}_{chunk.chunk_number}"
        metadata = {
            "url": chunk.url,
            "chunk_number": chunk.chunk_number,
            "title": chunk.title,
            "summary": chunk.summary,
            "text": chunk.content,
            **chunk.metadata
        }
        index.upsert(vectors=[{
            "id": chunk_id,
            "values": chunk.embedding,
            "metadata": metadata
        }])
        print(f"Upserted chunk {chunk.chunk_number} for {chunk.url}")
    except Exception as e:
        print(f"Error inserting chunk {chunk.chunk_number} for {chunk.url}: {e}")
        traceback.print_exc()

async def process_url(url: str):
    try:
        print(f"Processing: {url}")
        result = await crawler.arun(url=url, config=crawler_config, session_id="psu-session")

        if not result.success:
            print(f"Failed to crawl: {url} - {result.error_message}")
            failed_urls.append(url)
            return

        markdown = getattr(result.markdown, "cleaned_text", None) or result.markdown.raw_markdown
        if not markdown or len(markdown.strip()) < 300:
            print(f"Empty or too short content: {url}")
            return

        domain = urlparse(url).netloc
        crawled_at = datetime.now(timezone.utc).isoformat()
        chunks = chunk_text(markdown)

        # Filter out short or boilerplate chunks
        chunks = [c for c in chunks if len(c.strip()) >= 300 and "copyright" not in c.lower()]
        print(f"Split into {len(chunks)} quality chunks")

        for i, chunk_content in enumerate(chunks):
            title_summary = await get_title_and_summary(chunk_content, url)
            chunk = ProcessedChunk(
                url=url,
                chunk_number=i,
                title=title_summary.get("title", f"Chunk {i}"),
                summary=title_summary.get("summary", "No summary"),
                content=chunk_content,
                metadata={
                    "source": domain,
                    "section": result.page_title if hasattr(result, 'page_title') else "Unknown",
                    "content_type": "text/markdown",
                    "crawled_at": crawled_at,
                    "is_english": True,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "url_path": urlparse(url).path,
                    "content_length": len(chunk_content)
                }
            )
            await insert_chunk(chunk)

        print(f"Finished: {url} → {len(chunks)} chunks")
    except Exception as e:
        print(f"Error in process_url for {url}: {e}")
        traceback.print_exc()
        failed_urls.append(url)

def is_english_non_article_url(url: str) -> bool:
    blocked = ['/ar/', '/article/', '/news/', '/blog/', '/post/', 'article', 'news-item']
    return not any(b in url.lower() for b in blocked)

def get_psu_urls() -> List[str]:
    try:
        response = requests.get("https://www.psu.edu.sa/sitemap.xml", timeout=30)
        if response.status_code == 200:
            root = ElementTree.fromstring(response.content)
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            urls = [loc.text for loc in root.findall('.//sm:url/sm:loc', ns) if is_english_non_article_url(loc.text)]
            print(f"Found {len(urls)} crawlable URLs")
            return urls
    except Exception as e:
        print(f"Error fetching sitemap: {e}")
    return []

async def crawl_parallel(urls: List[str], max_concurrent: int = 10):
    await crawler.start()
    try:
        semaphore = asyncio.Semaphore(max_concurrent)
        async def limited(url):
            async with semaphore:
                await process_url(url)
        await asyncio.gather(*[limited(url) for url in urls])
    finally:
        await crawler.close()

async def main():
    print("Starting crawl...")
    urls = get_psu_urls()
    if not urls:
        print("No URLs found.")
        return

    try:
        initial_count = index.describe_stats().get('total_vector_count', 0)
    except:
        initial_count = 0

    await crawl_parallel(urls)

    try:
        final_count = index.describe_stats().get('total_vector_count', 0)
        print(f"Total new records: {final_count - initial_count}")
    except:
        print("Could not fetch final Pinecone stats")

    if failed_urls:
        print(f"Failed URLs ({len(failed_urls)}):")
        for url in failed_urls:
            print(" -", url)

if __name__ == "__main__":
    asyncio.run(main())
