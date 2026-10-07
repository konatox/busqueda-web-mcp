"""MCP tools. stdout is reserved exclusively for the stdio protocol."""

import logging
import ssl
import sys

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from typing import Annotated

from . import config
from .fetcher import fetch_page
from .search import SearchService

logger = logging.getLogger(__name__)
mcp = FastMCP("busqueda-web-mcp", log_level="WARNING")
search_service = SearchService()


def error_result(exc: Exception) -> dict:
    logger.warning("Tool failed (%s): %s", type(exc).__name__, exc, exc_info=True)
    causes = []
    cause = exc
    while cause is not None and all(cause is not item for item in causes):
        causes.append(cause)
        cause = cause.__cause__ or cause.__context__
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        message = "Request timed out"
    elif isinstance(exc, httpx.HTTPStatusError):
        message = f"Page returned HTTP {exc.response.status_code}"
    elif isinstance(exc, ValueError):
        message = str(exc)
    elif any(isinstance(cause, ssl.SSLCertVerificationError) for cause in causes):
        message = "Could not verify the page's TLS certificate"
    elif any(isinstance(cause, ssl.SSLError) for cause in causes):
        message = "Could not establish a secure TLS connection to the page"
    elif isinstance(exc, httpx.RequestError):
        message = "Could not connect to the page"
    else:
        message = "Search or download failed; try again later"
    return {"error": True, "message": message}


@mcp.tool()
async def web_search(query: Annotated[str, Field(min_length=1, max_length=config.MAX_QUERY_CHARS)],
                     max_results: Annotated[int, Field(strict=True, ge=1, le=config.MAX_SEARCH_RESULTS)] = config.DEFAULT_SEARCH_RESULTS) -> dict:
    """Search the public web for current or external information. Returns titles, URLs and short snippets. Use before fetch_url when you do not know the exact page."""
    try:
        return await search_service.search(query, max_results)
    except Exception as exc:
        return error_result(exc)


@mcp.tool()
async def fetch_url(url: Annotated[str, Field(min_length=1, max_length=config.MAX_URL_CHARS)],
                    max_chars: Annotated[int, Field(strict=True, ge=1, le=config.ABSOLUTE_MAX_PAGE_CHARS)] = config.DEFAULT_MAX_PAGE_CHARS) -> dict:
    """Read useful text from a public HTTP or HTTPS webpage. Use after web_search when more detail from a specific result is needed."""
    try:
        return await fetch_page(url, max_chars)
    except Exception as exc:
        return {"url": url, "title": "", "text": "", "truncated": False, **error_result(exc)}


def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s", force=True)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
