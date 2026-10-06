"""Telegram's one output dialect: HTML.

Escaping HTML is total -- `&`, `<` and `>` and nothing else -- so any value
can be interpolated safely; Markdown's escaping differs per dialect and a miss
makes Telegram refuse the whole message.
"""

import html
import re

from lxml import etree
from lxml import html as lxml_html
from markupsafe import Markup

MESSAGE_LIMIT = 4096
CAPTION_LIMIT = 1024

# The tags Telegram's HTML parse mode accepts, and what an Odoo tag becomes.
_KEPT = {"b", "i", "u", "s", "a", "code", "pre", "blockquote", "tg-spoiler"}
_RENAMED = {
    "strong": "b",
    "em": "i",
    "ins": "u",
    "del": "s",
    "strike": "s",
}
_BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLANK_LINES = re.compile(r"\n{3,}")
_TAG = re.compile(r"<[^>]+>")


def escape(value):
    """`value` as literal text inside Telegram HTML."""
    return html.escape("" if value is None else str(value), quote=False)


def bold(value) -> str:
    return f"<b>{escape(value)}</b>"


def italic(value) -> str:
    return f"<i>{escape(value)}</i>"


def code(value):
    return f"<code>{escape(value)}</code>"


def link(label, url):
    return f'<a href="{html.escape(url or "", quote=True)}">{escape(label)}</a>'


def plain(text):
    """Telegram HTML as the text a reader sees: the fallback when a message
    would not parse."""
    return html.unescape(_TAG.sub("", text or ""))


def from_odoo_html(markup, base_url=""):
    """Odoo HTML (a mail body) as Telegram HTML: supported tags kept, others
    unwrapped, block elements as line breaks, links absolute."""
    if not markup:
        return ""
    source = str(markup) if isinstance(markup, Markup) else markup
    try:
        root = lxml_html.fragment_fromstring(source, create_parent="div")
    except etree.ParserError, ValueError:
        return escape(source)
    parts = []
    _render(root, parts, base_url)
    return _BLANK_LINES.sub("\n\n", "".join(parts)).strip()


def _render(node, parts, base_url):
    tag = node.tag if isinstance(node.tag, str) else None
    tag = tag.lower() if tag else None
    name = _RENAMED.get(tag, tag)
    opened = None
    if tag in _HEADINGS:
        opened = "b"
    elif name in _KEPT:
        opened = name
    if tag == "br":
        parts.append("\n")
    if opened == "a":
        href = node.get("href") or ""
        if href.startswith("/") and base_url:
            href = base_url.rstrip("/") + href
        if href.startswith(("http://", "https://", "tg://", "mailto:")):
            parts.append(f'<a href="{html.escape(href, quote=True)}">')
        else:
            opened = None
    elif opened:
        parts.append(f"<{opened}>")
    if tag == "li":
        parts.append("• ")
    if node.text and tag is not None:
        parts.append(escape(node.text))
    for child in node:
        if isinstance(child.tag, str):
            _render(child, parts, base_url)
        if child.tail:
            parts.append(escape(child.tail))
    if opened:
        parts.append(f"</{opened}>")
    if tag in _BLOCKS and tag != "br":
        parts.append("\n")


def truncate(text, limit=MESSAGE_LIMIT, ellipsis="…"):
    """`text` cut to `limit` characters of what Telegram counts, never inside a
    tag or an entity, with every tag it leaves open closed."""
    if len(plain(text)) <= limit:
        return text
    out, visible, open_tags, i = [], 0, [], 0
    budget = limit - len(ellipsis)
    while i < len(text) and visible < budget:
        if text[i] == "<":
            end = text.index(">", i) + 1
            tag = text[i:end]
            name = tag.strip("</>").split()[0]
            if tag.startswith("</"):
                if open_tags and open_tags[-1] == name:
                    open_tags.pop()
            else:
                open_tags.append(name)
            out.append(tag)
            i = end
            continue
        if text[i] == "&":
            end = text.find(";", i)
            end = end + 1 if end != -1 else i + 1
            out.append(text[i:end])
            i = end
        else:
            out.append(text[i])
            i += 1
        visible += 1
    out.append(ellipsis)
    out.extend(f"</{name}>" for name in reversed(open_tags))
    return "".join(out)
