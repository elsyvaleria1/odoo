import logging
from html import unescape

import markupsafe
from lxml import etree, html

from odoo import api, models
from odoo.libs.text import plaintext_link_spans
from odoo.tools.mail import URL_SKIP_PROTOCOL_REGEX, is_html_empty

from odoo.addons.link_tracker.tools.html import (
    find_links_with_urls_and_labels,
    url_is_blacklisted,
)

_logger = logging.getLogger(__name__)

TEXT_SHORTEN_SKIP_PATHS = ("/r/",)


class MixinMailRender(models.AbstractModel):
    _inherit = "mixin.mail.render"


    @api.model
    def _shorten_links(self, body, link_tracker_vals, blacklist=None, base_url=None):
        if not body or is_html_empty(body):
            return body
        base_url = base_url or self.env.registry.settings.get(
            self.env, "web.base.url", False
        )
        short_schema = base_url + "/r/"

        try:
            fragments = html.fragments_fromstring(body)
        except etree.ParserError:
            _logger.warning(
                "link_tracker: could not parse an html body, leaving its links alone"
            )
            return body
        if not fragments:
            return body

        link_nodes, urls_and_labels = find_links_with_urls_and_labels(
            fragments,
            base_url,
            skip_regex=rf"^{URL_SKIP_PROTOCOL_REGEX}",
            skip_prefix=short_schema,
            skip_list=blacklist,
        )
        if not link_nodes:
            return body

        links_trackers = self.env["link.tracker"].search_or_create(
            [
                dict(link_tracker_vals, **url_and_label)
                for url_and_label in urls_and_labels
            ]
        )
        for node, link_tracker in zip(link_nodes, links_trackers, strict=True):
            node.set("href", link_tracker.short_url)

        new_html = "".join(
            fragment
            if isinstance(fragment, str)
            else html.tostring(fragment, encoding="unicode", method="xml")
            for fragment in fragments
        )
        if isinstance(body, markupsafe.Markup):
            new_html = markupsafe.Markup(new_html)

        return new_html

    @api.model
    def _shorten_links_text_skip_prefixes(self, base_url):
        return tuple(base_url + path for path in TEXT_SHORTEN_SKIP_PATHS)

    @api.model
    def _shorten_links_text(
        self, content, link_tracker_vals, blacklist=None, base_url=None
    ):
        if not content:
            return content
        base_url = base_url or self.env.registry.settings.get(
            self.env, "web.base.url", False
        )
        skip_prefixes = self._shorten_links_text_skip_prefixes(base_url)

        spans = plaintext_link_spans(content)
        original_urls = sorted({content[start:end] for start, end in spans})
        to_shorten = [
            url
            for url in original_urls
            if not url.startswith(skip_prefixes)
            and not url_is_blacklisted(url, blacklist)
        ]
        if not to_shorten:
            return content

        links = self.env["link.tracker"].search_or_create(
            [dict(link_tracker_vals, url=unescape(url)) for url in to_shorten]
        )
        short_urls = {
            url: link.short_url
            for url, link in zip(to_shorten, links, strict=True)
            if link.short_url
        }
        parts = []
        idx = 0
        for start, end in spans:
            if short_url := short_urls.get(content[start:end]):
                parts += (content[idx:start], short_url)
                idx = end
        parts.append(content[idx:])
        return "".join(parts)
