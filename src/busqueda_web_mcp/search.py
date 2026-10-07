"""Replaceable search provider and bounded optional TTL cache."""

import asyncio
import copy
import time
from collections import OrderedDict
from typing import Protocol

from bs4 import BeautifulSoup

from . import config
from .security import parse_url


class SearchProvider(Protocol):
    def search(self, query: str, max_results: int) -> list[dict[str, str]]: ...


def create_ddgs():
    # Lazy import permits an offline MCP health check before network dependencies
    # are available. Normal installation includes ddgs as a required dependency.
    from ddgs import DDGS

    return DDGS(timeout=config.REQUEST_TIMEOUT)


class DuckDuckGoProvider:
    def search(self, query: str, max_results: int) -> list[dict[str, str]]:
        # Explicit backend prevents DDGS from consulting Google or other providers.
        from ddgs.exceptions import TimeoutException
        from ddgs.engines import ENGINES

        # DDGS falls back to auto if a requested backend is unavailable. Fail
        # closed instead, so a dependency change cannot enable Google searches.
        if "duckduckgo" not in ENGINES.get("text", {}):
            raise ValueError("DuckDuckGo backend is unavailable; update ddgs")

        try:
            rows = create_ddgs().text(query, max_results=max_results, backend="duckduckgo")
        except TimeoutException as exc:
            raise TimeoutError("DuckDuckGo request timed out") from exc
        results = []
        seen = set()
        for row in rows:
            try:
                url = str(parse_url(row.get("href", "")))
            except ValueError:
                continue
            if url in seen:
                continue
            seen.add(url)
            results.append({
                "title": clean(row.get("title", ""), config.MAX_TITLE_CHARS),
                "url": url,
                "snippet": clean(row.get("body", ""), config.MAX_SNIPPET_CHARS),
            })
            if len(results) >= max_results:
                break
        return results


def clean(value: str, limit: int) -> str:
    return " ".join(BeautifulSoup(str(value), "html.parser").get_text(" ").split())[:limit]


class SearchService:
    def __init__(self, provider: SearchProvider | None = None, cache_enabled: bool | None = None):
        self.provider = provider or DuckDuckGoProvider()
        self.cache_enabled = config.CACHE_ENABLED if cache_enabled is None else cache_enabled
        self.cache: OrderedDict[tuple[str, int], tuple[float, list[dict[str, str]]]] = OrderedDict()

    async def search(self, query: str, max_results: int = config.DEFAULT_SEARCH_RESULTS) -> dict:
        config.bounded_int(max_results, "max_results", config.MAX_SEARCH_RESULTS)
        if not isinstance(query, str) or not query.strip() or len(query) > config.MAX_QUERY_CHARS:
            raise ValueError(f"query must contain 1 to {config.MAX_QUERY_CHARS} characters")
        query = query.strip()
        key = (query, max_results)
        if self.cache_enabled and key in self.cache:
            deadline, rows = self.cache[key]
            if deadline > time.monotonic():
                self.cache.move_to_end(key)
                return {"query": query, "results": copy.deepcopy(rows)}
            del self.cache[key]
        rows = await asyncio.wait_for(
            asyncio.to_thread(self.provider.search, query, max_results), config.REQUEST_TIMEOUT
        )
        rows = rows[:max_results]
        if self.cache_enabled:
            self.cache[key] = (time.monotonic() + config.CACHE_TTL_SECONDS, copy.deepcopy(rows))
            self.cache.move_to_end(key)
            while len(self.cache) > config.CACHE_MAX_ENTRIES:
                self.cache.popitem(last=False)
        return {"query": query, "results": rows}
