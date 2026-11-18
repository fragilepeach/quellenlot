"""Extract readable text from static article HTML."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Final

_REGIONS: Final = ("article", "main")
_SKIP: Final = {"aside", "footer", "form", "nav", "noscript", "script", "style", "svg", "template"}
_BLOCKS: Final = {
    "article",
    "blockquote",
    "br",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "main",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
}
_PAYWALL: Final = re.compile(r'"isAccessibleForFree"\s*:\s*(?:false|"false")(?=\s*[,}])', re.I)
_META_CHARSET: Final = re.compile(br"""<meta\b[^>]*?\bcharset\s*=\s*["']?([a-z0-9_-]+)""", re.I)


@dataclass(frozen=True)
class ArticleText:
    """Text and availability cues derived from the captured HTML."""

    title: str
    text: str
    in_article_element: bool
    paywall_indicated: bool


def _normalize(parts: list[str]) -> str:
    lines = (" ".join(line.split()) for line in "".join(parts).splitlines())
    return "\n".join(line for line in lines if line)


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_head = False
        self._in_title = False
        self._structured_data = False
        self._paywall_indicated = False
        self._title: list[str] = []
        self._page: list[str] = []
        self._skipped: list[str] = []
        self._depth = dict.fromkeys(_REGIONS, 0)
        self._regions: dict[str, list[list[str]]] = {tag: [] for tag in _REGIONS}

    def _append(self, text: str) -> None:
        self._page.append(text)
        for tag in _REGIONS:
            if self._depth[tag]:
                self._regions[tag][-1].append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track content regions, structural breaks, title and paywall signals."""
        if tag in _SKIP:
            self._skipped.append(tag)
            if tag == "script":
                self._structured_data = ("type", "application/ld+json") in attrs
            return
        if self._skipped:
            return
        values = dict(attrs)
        if "data-paywall" in values and values["data-paywall"] not in {"false", "0"}:
            self._paywall_indicated = True
        if tag == "head":
            self._in_head = True
        if tag == "title":
            self._in_title = True
        if tag in self._depth:
            if self._depth[tag] == 0:
                self._regions[tag].append([])
            self._depth[tag] += 1
        if tag in _BLOCKS:
            self._append("\n")

    def handle_endtag(self, tag: str) -> None:
        """Close content regions and preserve block boundaries."""
        if self._skipped:
            if tag == self._skipped[-1]:
                self._skipped.pop()
            if tag == "script":
                self._structured_data = False
            return
        if tag == "head":
            self._in_head = False
        if tag == "title":
            self._in_title = False
        if tag in _BLOCKS:
            self._append("\n")
        if tag in self._depth and self._depth[tag]:
            self._depth[tag] -= 1

    def handle_data(self, data: str) -> None:
        """Collect readable text and inspect structured availability metadata."""
        if self._structured_data and _PAYWALL.search(data):
            self._paywall_indicated = True
        if self._skipped:
            return
        if self._in_title:
            self._title.append(data)
        elif not self._in_head:
            self._append(data)

    def extract(self) -> ArticleText:
        """Prefer the largest article region, then main content, then visible page text."""
        title = " ".join("".join(self._title).split())
        for tag in _REGIONS:
            text = max((_normalize(parts) for parts in self._regions[tag]), key=len, default="")
            if text:
                return ArticleText(title, text, tag == "article", self._paywall_indicated)
        return ArticleText(title, _normalize(self._page), False, self._paywall_indicated)


def extract_article(html: bytes, charset: str | None) -> ArticleText:
    """Decode and extract a snapshot from a static HTML document."""
    if charset is None:
        meta = _META_CHARSET.search(html[:4096])
        charset = meta[1].decode("ascii") if meta else "utf-8-sig"
    try:
        decoded = html.decode(charset)
    except (LookupError, UnicodeError):
        try:
            decoded = html.decode("utf-8-sig")
        except UnicodeError:
            decoded = html.decode("windows-1252", errors="replace")
    parser = _ArticleParser()
    parser.feed(decoded)
    parser.close()
    return parser.extract()
