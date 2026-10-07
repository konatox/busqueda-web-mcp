"""Bounded streaming download, manual safe redirects and readable extraction."""

import asyncio
import re
from contextlib import asynccontextmanager
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from . import config
from .security import Target, resolve_target


class FetchError(ValueError):
    pass


@asynccontextmanager
async def stream_target(client: httpx.AsyncClient, target: Target):
    # Try every validated address if TCP/TLS setup fails. Never retry a body,
    # HTTP status or redirect, and keep the caller's overall deadline.
    addresses = target.addresses or (target.address,)
    for index, address in enumerate(addresses):
        request = client.build_request(
            "GET", target.url.copy_with(host=address),
            headers={"Host": target.host_header},
            extensions={"sni_hostname": target.url.raw_host.decode("ascii")},
        )
        try:
            response = await client.send(request, stream=True)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if index == len(addresses) - 1:
                raise
            continue
        try:
            yield response
        finally:
            await response.aclose()
        return


def extract_html(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = " ".join(soup.title.get_text(" ", strip=True).split()) if soup.title else ""
    for tag in soup.select("script, style, nav, footer, body > header, aside, form, noscript, svg, template, [hidden], [aria-hidden='true'], [role='navigation'], [role='menu'], [role='contentinfo']"):
        tag.decompose()
    root = soup.select_one("main, [role='main'], article") or soup.body or soup
    blocks = []
    seen = set()
    for tag in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote", "td", "th"]):
        # Avoid emitting the same text from nested paragraphs/lists twice.
        if tag.find_parent(["li", "pre", "blockquote", "td", "th"]) is not None:
            continue
        text = " ".join(tag.get_text(" ", strip=True).split())
        if text and text not in seen:
            seen.add(text)
            blocks.append(("- " if tag.name == "li" else "") + text)
    text = "\n\n".join(blocks) if blocks else root.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return title[:config.MAX_TITLE_CHARS], text


async def fetch_page(url: str, max_chars: int = config.DEFAULT_MAX_PAGE_CHARS) -> dict:
    config.bounded_int(max_chars, "max_chars", config.ABSOLUTE_MAX_PAGE_CHARS)
    # Overall deadline includes DNS, redirects and body transfer.
    async with asyncio.timeout(config.REQUEST_TIMEOUT):
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT, follow_redirects=False, trust_env=False,
                                     headers={"User-Agent": config.USER_AGENT, "Accept": "text/html, text/plain, application/xhtml+xml"}) as client:
            current = url
            for hop in range(config.MAX_REDIRECTS + 1):
                target = await resolve_target(current)
                # Pin IP while preserving original Host and TLS certificate verification.
                async with stream_target(client, target) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if hop == config.MAX_REDIRECTS:
                            raise FetchError("Too many redirects")
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("Redirect has no destination")
                        current = urljoin(str(target.url), location)
                        continue
                    response.raise_for_status()
                    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if media_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                        raise FetchError("Unsupported Content-Type; only HTML and plain text are supported")
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=16384):
                        body.extend(chunk)
                        if len(body) > config.MAX_RESPONSE_BYTES:
                            raise FetchError("Page exceeds the download size limit")
                    # aiter_bytes already decompresses the body; retain only the
                    # content type for charset decoding, not Content-Encoding.
                    decoded = httpx.Response(200, headers={
                        "Content-Type": response.headers["content-type"],
                    }, content=bytes(body)).text
                    title, text = extract_html(decoded) if media_type != "text/plain" else ("", decoded.strip())
                    return {"url": str(target.url), "title": title, "text": text[:max_chars], "truncated": len(text) > max_chars}
    raise FetchError("Could not read page")
