"""Small, centralized limits. Restart the MCP after changing these values."""

MAX_SEARCH_RESULTS = 8
DEFAULT_SEARCH_RESULTS = 5
REQUEST_TIMEOUT = 10
DEFAULT_MAX_PAGE_CHARS = 12000
ABSOLUTE_MAX_PAGE_CHARS = 30000
MAX_SEARCH_AND_READ_PAGES = 3
MAX_QUERY_CHARS = 500
MAX_URL_CHARS = 4096
MAX_RESPONSE_BYTES = 2_000_000
MAX_REDIRECTS = 5
MAX_TITLE_CHARS = 300
MAX_SNIPPET_CHARS = 500
USER_AGENT = "busqueda-web-mcp/1.0"
CACHE_ENABLED = True
CACHE_TTL_SECONDS = 300
CACHE_MAX_ENTRIES = 100


def bounded_int(value: int, name: str, maximum: int) -> int:
    """Reject non-integers and invalid bounds rather than silently expanding work."""
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value
