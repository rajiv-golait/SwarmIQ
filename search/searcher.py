import hashlib
import logging
import time
from dataclasses import dataclass, field

import requests
import trafilatura
try:
    from ddgs import DDGS  # renamed package (ddgs >= 1.0)
except ImportError:
    from duckduckgo_search import DDGS  # fallback for older installs
from tenacity import (
    retry, stop_after_attempt,
    wait_exponential, retry_if_exception_type,
)

from search.cache import get as cache_get, put as cache_put
from utils.config import (
    JINA_BASE_URL,
    JINA_TIMEOUT_S,
    DDG_MAX_RESULTS,
    SEARCH_POLITE_DELAY_S,
)
from utils.progress import emit_progress

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    url:            str
    title:          str
    content:        str
    published_date: str = ""

    @property
    def chunk_id(self) -> str:
        return hashlib.sha256(
            f"{self.url}::{self.content[:300]}".encode()
        ).hexdigest()[:24]


class WebSearcher:
    """DuckDuckGo search + Jina Reader full-page extraction.

    Free, unlimited, no API key required.
    trafilatura as fallback when Jina fails.
    Results cached 24h to prevent re-fetching identical queries.
    """

    def __init__(self):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; ResearchBot/1.0)"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=10),
        retry=retry_if_exception_type(Exception),
    )
    def _ddg_search(self, query: str, max_results: int) -> list[dict]:
        ddgs = DDGS()
        return list(ddgs.text(query, max_results=max_results))

    def _fetch_jina(self, url: str) -> str:
        try:
            resp = self._session.get(
                f"{JINA_BASE_URL}{url}",
                headers={"Accept": "text/plain"},
                timeout=JINA_TIMEOUT_S,
            )
            if resp.status_code == 200 and len(resp.text) > 200:
                return resp.text[:2000]
        except Exception as e:
            logger.debug(f"Jina failed for {url}: {e}")
        return ""

    def _fetch_trafilatura(self, url: str) -> str:
        try:
            html = trafilatura.fetch_url(url)
            if html:
                text = trafilatura.extract(
                    html, include_comments=False, include_tables=True
                )
                return (text or "")[:2000]
        except Exception as e:
            logger.debug(f"Trafilatura failed for {url}: {e}")
        return ""

    def search(self, query: str, max_results: int = DDG_MAX_RESULTS) -> list[SearchResult]:
        """Search and retrieve full-page content. Returns cached if available."""
        cached = cache_get(query)
        if cached is not None:
            return [SearchResult(**r) for r in cached]

        emit_progress(f"[Search] DDG+Jina: {query[:72]}{'...' if len(query) > 72 else ''}")

        raw_results = []
        try:
            raw_results = self._ddg_search(query, max_results=max_results)
        except Exception as e:
            logger.error(f"DDG search failed '{query}': {e}")
            return []

        results = []
        for item in raw_results:
            url     = item.get("href", "")
            title   = item.get("title", "")
            snippet = item.get("body", "")

            if not url:
                continue

            content = self._fetch_jina(url)
            if len(content) < 200:
                content = self._fetch_trafilatura(url)
            if len(content) < 100:
                content = snippet

            if not content.strip():
                continue

            results.append(SearchResult(
                url=url, title=title, content=content[:2000]
            ))
            if SEARCH_POLITE_DELAY_S > 0:
                time.sleep(SEARCH_POLITE_DELAY_S)

        # Cache for next time
        cache_put(query, [
            {"url": r.url, "title": r.title,
             "content": r.content, "published_date": r.published_date}
            for r in results
        ])

        logger.info(f"Search '{query[:50]}': {len(results)} results")
        return results

    def multi_search(
        self, queries: list[str], max_per_query: int = 5
    ) -> list[SearchResult]:
        """Multiple queries, deduplicated by URL."""
        seen: set[str] = set()
        all_results: list[SearchResult] = []
        for q in queries:
            for r in self.search(q, max_results=max_per_query):
                if r.url not in seen:
                    seen.add(r.url)
                    all_results.append(r)
        return all_results
