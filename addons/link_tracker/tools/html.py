import re
from collections.abc import Iterable

from lxml import etree, html

MAX_LABEL_LENGTH = 512


def url_is_blacklisted(url: str, patterns: Iterable[str] | None) -> bool:
    if not patterns:
        return False
    return any(re.search(re.escape(item) + r"([#?/]|$)", url) for item in patterns)


def find_links_with_urls_and_labels(
    root_nodes, base_url, skip_regex=None, skip_prefix=None, skip_list=None
) -> tuple:
    link_nodes, urls_and_labels = [], []
    if isinstance(root_nodes, etree._Element):
        root_nodes = [root_nodes]

    for root_node in root_nodes:
        if isinstance(root_node, str):
            continue
        for link_node in root_node.iter(tag="a"):
            original_url = link_node.get("href")
            if not original_url:
                continue
            absolute_url = (
                base_url + original_url
                if original_url.startswith(("/", "?", "#"))
                else original_url
            )
            if (
                (skip_regex and re.search(skip_regex, absolute_url))
                or (skip_prefix and absolute_url.startswith(skip_prefix))
                or url_is_blacklisted(absolute_url, skip_list)
            ):
                continue

            if link_node.text and (stripped_text := link_node.text.strip()):
                label = stripped_text[:MAX_LABEL_LENGTH]
            else:
                children = list(link_node)
                label = _get_label_from_elements(children)[:MAX_LABEL_LENGTH]

            link_nodes.append(link_node)
            urls_and_labels.append({"url": absolute_url, "label": label})

    return link_nodes, urls_and_labels


def _get_label_from_elements(
    elements: Iterable[etree._Element], image_prefix: str = "[media] "
) -> str:
    for element in elements:
        if element.tag == "img":
            if img_alt := element.get("alt"):
                return f"{image_prefix}{img_alt}"
            if img_src := element.get("src"):
                img_src_tail = img_src.split("/")[-1]
                return f"{image_prefix}{img_src_tail}"
            return ""
        if isinstance(element, html.HtmlComment):
            continue
        if element.tag == "p" and element.get("class") == "o_outlook_hack":
            children = list(element)
            if label := _get_label_from_elements(children):
                return label
    return ""
