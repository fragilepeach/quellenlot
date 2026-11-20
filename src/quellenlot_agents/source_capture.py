"""Capture public article URLs as versioned source snapshots."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import IPv6Address, ip_address, ip_network
from typing import Final

import httpx
from pydantic import AnyHttpUrl, ValidationError

from quellenlot_agents.article_html import extract_article
from quellenlot_agents.models import SourceInput, SourceLink, SourceRetrieval

_DEFAULT_PORTS: Final = {"http": 80, "https": 443}
_REDIRECTS: Final = {301, 302, 303, 307, 308}
_HTML_TYPES: Final = {"text/html", "application/xhtml+xml"}
_MAX_HTML_BYTES: Final = 2 * 1024 * 1024
_MAX_SOURCE_CHARS: Final = 200_000
_MAX_LINKS: Final = 30
_TRACKING_PARAMETERS: Final = frozenset({"fbclid", "gclid", "msclkid"})
_TRANSLATED_IPV6: Final = (
    ip_network("64:ff9b::/96"),
    ip_network("64:ff9b:1::/48"),
    ip_network("2002::/16"),
    ip_network("2001::/32"),
)


class _RetrievalError(RuntimeError):
    """A URL could not yield a usable article snapshot."""

    def __init__(self, message: str, response_url: httpx.URL | None = None) -> None:
        super().__init__(message)
        self.response_url = response_url


@dataclass(frozen=True)
class _Page:
    url: httpx.URL
    body: bytes
    charset: str | None
    partial: bool


def url_key(url: AnyHttpUrl) -> str:
    """Normalize a URL for matching while leaving the recorded link intact.

    Args:
        url: Validated HTTP(S) URL from input, search or article HTML.

    Returns:
        The URL without fragments or common tracking parameters.
    """
    parsed = httpx.URL(str(url))
    params = tuple(
        (key, value)
        for key, value in parsed.params.multi_items()
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_PARAMETERS
    )
    query = str(httpx.QueryParams(params)).encode("ascii") if params else None
    return str(parsed.copy_with(fragment=None, query=query))


def _article_links(
    page_url: httpx.URL, text: str, links: tuple[tuple[str, str], ...]
) -> tuple[list[SourceLink], bool]:
    """Resolve and retain links anchored in the saved text."""
    current = url_key(AnyHttpUrl(str(page_url)))
    seen: set[tuple[str, str]] = set()
    results: list[SourceLink] = []
    for href, anchor in links:
        if href.lstrip().startswith("#") or len(anchor) > 500 or anchor not in text:
            continue
        try:
            destination = page_url.join(href)
            if destination.userinfo or destination.port not in {
                None,
                _DEFAULT_PORTS.get(destination.scheme),
            }:
                continue
            url = AnyHttpUrl(str(destination))
            key = url_key(url)
        except (httpx.InvalidURL, ValidationError):
            continue
        if key == current or (key, anchor) in seen:
            continue
        if len(results) >= _MAX_LINKS:
            return results, True
        seen.add((key, anchor))
        results.append(SourceLink(url=url, anchor=anchor))
    return results, False


async def _public_addresses(url: httpx.URL) -> list[str]:
    """Reject URLs whose scheme, credentials, port, or resolved addresses are unsafe."""
    port = _DEFAULT_PORTS.get(url.scheme)
    if port is None or url.port not in {None, port} or not url.host or url.userinfo:
        msg = "Source URLs must use public HTTP(S), default ports and no credentials."
        raise _RetrievalError(msg)
    host = url.raw_host.decode("ascii")
    records = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = {ip_address(record[4][0]) for record in records}
    if not addresses or any(
        not address.is_global
        or address.is_multicast
        or address.is_reserved
        or (
            isinstance(address, IPv6Address)
            and (
                address.ipv4_mapped is not None
                or address.scope_id is not None
                or any(address in network for network in _TRANSLATED_IPV6)
            )
        )
        for address in addresses
    ):
        msg = "Source URL did not resolve exclusively to public Internet addresses."
        raise _RetrievalError(msg)
    ordered = sorted(addresses, key=lambda item: (item.version, int(item)))
    return [str(address) for address in ordered]


async def _download(url: httpx.URL, address: str) -> _Page | httpx.URL:
    """Read one bounded HTML response or return its redirect without following it."""
    # Pin the connection to the checked address, retaining the hostname for HTTP and TLS.
    # The fresh client prevents connection and cookie reuse across different hostnames.
    pinned_url = url.copy_with(host=address, fragment=None)
    hostname = url.raw_host.decode("ascii")
    headers = {
        "Host": url.netloc.decode("ascii"),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Encoding": "identity",
        "User-Agent": "Quellenlot/0.1",
    }
    async with (
        httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=4.0),
            follow_redirects=False,
            trust_env=False,
        ) as client,
        client.stream(
            "GET",
            pinned_url,
            headers=headers,
            extensions={"sni_hostname": hostname},
        ) as response,
    ):
        if response.status_code in _REDIRECTS:
            location = response.headers.get("location")
            if not location:
                msg = "Source redirected without a destination."
                raise _RetrievalError(msg, url)
            return url.join(location)
        if not response.is_success:
            msg = f"Source returned HTTP {response.status_code}."
            raise _RetrievalError(msg, url)
        media_type = response.headers.get("content-type", "").partition(";")[0].strip().lower()
        if media_type not in _HTML_TYPES:
            msg = "Source did not return an HTML article."
            raise _RetrievalError(msg, url)
        if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
            msg = "Source returned an unsupported compressed response."
            raise _RetrievalError(msg, url)
        body = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=65536):
            if len(body) + len(chunk) > _MAX_HTML_BYTES:
                msg = "Source response exceeded the HTML size limit."
                raise _RetrievalError(msg, url)
            body.extend(chunk)
        return _Page(url, bytes(body), response.charset_encoding, response.status_code == 206)


async def _download_from_public_address(url: httpx.URL) -> _Page | httpx.URL:
    """Retry connection failures against the other validated addresses for this host."""
    last_error: httpx.ConnectError | httpx.ConnectTimeout | None = None
    for address in await _public_addresses(url):
        try:
            result = await _download(url, address)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            last_error = exc
        else:
            return result
    msg = "Could not establish a connection to the source."
    raise _RetrievalError(msg) from last_error


async def _fetch_page(original_url: AnyHttpUrl) -> _Page:
    """Resolve and validate each redirect destination independently."""
    url = httpx.URL(str(original_url)).copy_with(fragment=None)
    for _ in range(6):
        page = await _download_from_public_address(url)
        if isinstance(page, _Page):
            return page
        url = page.copy_with(fragment=None)
    msg = "Source exceeded the redirect limit."
    raise _RetrievalError(msg)


def _snapshot(
    page: _Page,
    source_id: str,
    requested_url: AnyHttpUrl,
) -> tuple[SourceInput, SourceRetrieval]:
    """Create a versioned snapshot and record visible limits on its completeness."""
    try:
        content = extract_article(page.body, page.charset)
    except (AssertionError, ValueError) as exc:
        msg = "Source HTML could not be parsed."
        raise _RetrievalError(msg, page.url) from exc
    if not content.text:
        msg = "No readable article text was found in the HTML."
        raise _RetrievalError(msg, page.url)
    partial_reasons: list[str] = []
    if page.partial:
        partial_reasons.append("The server returned partial content.")
    if content.paywall_indicated:
        partial_reasons.append("The page indicates restricted access.")
    if not content.in_article_element:
        partial_reasons.append("Page text was used because no readable article element was found.")
    if len(content.text) > _MAX_SOURCE_CHARS:
        partial_reasons.append("Text was clipped to the snapshot size limit.")

    captured_at = datetime.now(UTC)
    final_url = AnyHttpUrl(str(page.url))
    source = SourceInput(
        source_id=source_id,
        version_id=captured_at.isoformat(),
        title=(content.title or page.url.host)[:500],
        url=final_url,
        captured_at=captured_at,
        published_at=content.published_at,
        updated_at=content.updated_at,
        text=content.text[:_MAX_SOURCE_CHARS],
        text_is_complete=False,
    )
    detail = " ".join(partial_reasons) or "Article text captured. Completeness is unverified."
    links, links_limited = _article_links(page.url, source.text, content.links)
    return source, SourceRetrieval(
        source_id=source_id,
        requested_url=requested_url,
        final_url=final_url,
        status="partial" if partial_reasons else "captured",
        detail=detail,
        retrieved_at=captured_at,
        snapshot=source,
        links=links,
        links_limited=links_limited,
    )


async def capture_source(
    url: AnyHttpUrl,
    source_id: str,
) -> tuple[SourceInput | None, SourceRetrieval]:
    """Fetch and extract a source, including explicit errors and incomplete captures.

    Args:
        url: Public article URL to fetch and validate through redirects.
        source_id: Unique case-local identifier for the retrieved snapshot.

    Returns:
        A snapshot when readable text is available and a retrieval record in every case.
    """
    final_url: AnyHttpUrl | None = None
    try:
        async with asyncio.timeout(20):
            page = await _fetch_page(url)
        result = _snapshot(page, source_id, url)
    except _RetrievalError as exc:
        detail = str(exc)
        if exc.response_url is not None:
            final_url = AnyHttpUrl(str(exc.response_url))
    except TimeoutError:
        detail = "Source retrieval timed out."
    except (httpx.HTTPError, httpx.InvalidURL, OSError):
        detail = "Source retrieval failed while resolving, connecting or reading the page."
    else:
        return result
    return None, SourceRetrieval(
        source_id=source_id,
        requested_url=url,
        final_url=final_url,
        status="failed",
        detail=detail,
        retrieved_at=datetime.now(UTC),
    )
