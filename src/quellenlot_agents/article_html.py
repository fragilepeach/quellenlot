"""Extract readable text from static article HTML."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Final, Literal, override

from pydantic import JsonValue, RootModel, ValidationError

from quellenlot_agents.models import DateProvenance, SourceDate

_REGIONS: Final[tuple[str, ...]] = ("article", "main")
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
_PAYWALL: Final = re.compile(
    r'"isAccessibleForFree"\s*:\s*(?:false|"false")(?=\s*[,}])', re.IGNORECASE
)
_META_CHARSET: Final = re.compile(
    rb"""<meta\b[^>]*?\bcharset\s*=\s*["']?([a-z0-9_-]+)""", re.IGNORECASE
)
_ISO_DATE_PREFIX: Final = re.compile(r"^\d{4}-\d{2}-\d{2}(?:$|[T ]\d{2}:\d{2})")
type _DateKind = Literal["published", "updated"]
_OPEN_GRAPH: Final[dict[str, _DateKind]] = {
    "article:published_time": "published",
    "article:modified_time": "updated",
}
_HTML_TIME: Final[dict[str, _DateKind]] = {"datepublished": "published", "datemodified": "updated"}
_DATE_PRIORITY: Final[tuple[DateProvenance, ...]] = ("json_ld", "open_graph", "html_time")


class _StructuredData(RootModel[JsonValue]):
    """Validate an arbitrary JSON-LD value before inspecting article nodes."""


@dataclass(frozen=True)
class ArticleText:
    """Text and availability cues derived from the captured HTML."""

    title: str
    text: str
    in_article_element: bool
    paywall_indicated: bool
    published_at: SourceDate | None = None
    updated_at: SourceDate | None = None
    publisher: str | None = None
    authors: tuple[str, ...] = ()


def _normalize(parts: list[str]) -> str:
    lines = (" ".join(line.split()) for line in "".join(parts).splitlines())
    return "\n".join(line for line in lines if line)


def _parse_date(text: str) -> date | datetime | None:
    """Preserve the stated date precision and offset without filling in absent metadata."""
    value = text.strip()
    if not _ISO_DATE_PREFIX.match(value):
        return None
    try:
        return date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value)
    except ValueError:
        return None


def _article_type(value: JsonValue) -> bool:
    names = value if isinstance(value, list) else [value]
    terms = (
        name.rsplit("/", 1)[-1].rsplit(":", 1)[-1].lower()
        for name in names
        if isinstance(name, str)
    )
    return any(term.endswith("article") or term == "blogposting" for term in terms)


def _json_ld_dates(data: str) -> Iterator[tuple[_DateKind, str]]:
    """Read declarations on article entities and avoid dates on page or publisher nodes."""
    try:
        graph = _StructuredData.model_validate_json(data).root
    except ValidationError:
        return
    pending = [graph]
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(node)
        elif isinstance(node, dict):
            if _article_type(node.get("@type")):
                published = node.get("datePublished")
                updated = node.get("dateModified")
                if isinstance(published, str):
                    yield "published", published
                if isinstance(updated, str):
                    yield "updated", updated
            pending.extend([node.get("@graph"), node.get("mainEntity")])


def _entity_names(value: JsonValue) -> Iterator[str]:
    """Read named entities from common JSON-LD person and organization structures."""
    if isinstance(value, list):
        for item in value:
            yield from _entity_names(item)
    elif isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            yield name.strip()
    elif (
        isinstance(value, str)
        and value.strip()
        and not value.lstrip().lower().startswith(("http://", "https://"))
    ):
        yield value.strip()


def _json_ld_attribution(data: str) -> Iterator[tuple[str, str]]:
    """Extract author and publisher names declared on article entities."""
    try:
        graph = _StructuredData.model_validate_json(data).root
    except ValidationError:
        return
    pending = [graph]
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            pending.extend(node)
        elif isinstance(node, dict):
            if _article_type(node.get("@type")):
                for name in _entity_names(node.get("publisher")):
                    yield "publisher", name
                for name in _entity_names(node.get("author")):
                    yield "author", name
            pending.extend([node.get("@graph"), node.get("mainEntity")])


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
        self._depth: dict[str, int] = dict.fromkeys(_REGIONS, 0)
        self._regions: dict[str, list[list[str]]] = {tag: [] for tag in _REGIONS}
        self._dates: dict[_DateKind, dict[DateProvenance, set[date | datetime]]] = {
            "published": {},
            "updated": {},
        }
        self._publishers: dict[str, set[str]] = {"json_ld": set(), "open_graph": set()}
        self._authors: dict[str, set[str]] = {"json_ld": set(), "meta": set()}

    def _record_date(
        self, kind: _DateKind | None, text: str | None, origin: DateProvenance
    ) -> None:
        if kind is not None and text is not None:
            value = _parse_date(text)
            if value is not None:
                self._dates[kind].setdefault(origin, set()).add(value)

    def _source_date(self, kind: _DateKind) -> SourceDate | None:
        """Use the best available metadata channel if its declarations agree."""
        for origin in _DATE_PRIORITY:
            dates = self._dates[kind].get(origin)
            if dates is not None:
                if len(dates) != 1:
                    return None
                return SourceDate(value=next(iter(dates)), provenance=origin)
        return None

    def _append(self, text: str) -> None:
        self._page.append(text)
        for tag in _REGIONS:
            if self._depth[tag]:
                self._regions[tag][-1].append(text)

    @override
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
        if tag == "meta":
            kind = _OPEN_GRAPH.get((values.get("property") or "").lower())
            self._record_date(kind, values.get("content"), "open_graph")
            if (values.get("property") or "").lower() == "og:site_name":
                name = values.get("content")
                if name is not None and name.strip():
                    self._publishers["open_graph"].add(name.strip())
            if (values.get("name") or "").lower() == "author":
                name = values.get("content")
                if name is not None and name.strip():
                    self._authors["meta"].add(name.strip())
        elif tag == "time" and self._depth["article"]:
            kind = _HTML_TIME.get((values.get("itemprop") or "").lower())
            self._record_date(kind, values.get("datetime"), "html_time")
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

    @override
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
        if self._depth.get(tag, 0):
            self._depth[tag] -= 1

    @override
    def handle_data(self, data: str) -> None:
        """Collect readable text and inspect structured availability metadata."""
        if self._structured_data:
            if _PAYWALL.search(data):
                self._paywall_indicated = True
            for kind, value in _json_ld_dates(data):
                self._record_date(kind, value, "json_ld")
            for kind, value in _json_ld_attribution(data):
                if kind == "publisher":
                    self._publishers["json_ld"].add(value)
                else:
                    self._authors["json_ld"].add(value)
        if self._skipped:
            return
        if self._in_title:
            self._title.append(data)
        elif not self._in_head:
            self._append(data)

    def extract(self) -> ArticleText:
        """Prefer the largest article region, then main content, then visible page text."""
        title = " ".join("".join(self._title).split())
        published_at = self._source_date("published")
        updated_at = self._source_date("updated")
        publishers = self._publishers["json_ld"] or self._publishers["open_graph"]
        publisher = next(iter(publishers)) if len(publishers) == 1 else None
        authors = tuple(sorted(self._authors["json_ld"] or self._authors["meta"]))
        for tag in _REGIONS:
            text = max((_normalize(parts) for parts in self._regions[tag]), key=len, default="")
            if text:
                return ArticleText(
                    title,
                    text,
                    tag == "article",
                    self._paywall_indicated,
                    published_at,
                    updated_at,
                    publisher,
                    authors,
                )
        return ArticleText(
            title,
            _normalize(self._page),
            False,
            self._paywall_indicated,
            published_at,
            updated_at,
            publisher,
            authors,
        )


def extract_article(html: bytes, charset: str | None) -> ArticleText:
    """Decode and extract a snapshot from a static HTML document.

    Args:
        html: Bounded response bytes from the source page.
        charset: Declared HTTP character encoding, when available.

    Returns:
        The readable article, declared dates, and signals of restricted or fallback extraction.
    """
    if charset is None:
        meta = _META_CHARSET.search(html[:4096])
        match = meta.group(1) if meta is not None else None
        if isinstance(match, bytes):
            charset = match.decode("ascii")
    try:
        decoded = html.decode(charset or "utf-8-sig")
    except (LookupError, UnicodeError):
        try:
            decoded = html.decode("utf-8-sig")
        except UnicodeError:
            decoded = html.decode("windows-1252", errors="replace")
    parser = _ArticleParser()
    parser.feed(decoded)
    parser.close()
    return parser.extract()
