from odoo.tests import common, tagged
from odoo.tools import mute_logger

from odoo.addons.link_tracker.tests.common import MockLinkTracker


@tagged("post_install", "-at_install")
class TestTrackerHttpRequests(MockLinkTracker, common.HttpCase):
    def test_outgoing_links_ignore_visitor_attribution_over_http(self):
        wanted = self.env["utm.source"].create({"name": "Wanted source"})
        plain, attributed = self.env["link.tracker"].create(
            [
                {"url": "https://outgoing.example.com", "source_id": False},
                {"url": "https://outgoing.example.com", "source_id": wanted.id},
            ]
        )
        self.authenticate("admin", "admin")
        for context, expected in (
            ({}, plain),
            ({"default_source_id": wanted.id}, attributed),
        ):
            with self.subTest(context=context):
                found_ids = self.call_jsonrpc(
                    "/web/dataset/call_kw/link.tracker/search_or_create",
                    {
                        "model": "link.tracker",
                        "method": "search_or_create",
                        "args": [[{"url": plain.url}]],
                        "kwargs": {"context": context},
                    },
                    cookies={"odoo_utm_source": "Unrelated visitor source"},
                )
                self.assertEqual(found_ids, expected.ids)
        self.assertFalse(
            self.env["utm.source"].search([("name", "=", "Unrelated visitor source")])
        )

    @mute_logger("odoo.addons.http_routing.models.ir_http", "odoo.http")
    def test_no_preview_tracking(self):
        link_tracker = self.env["link.tracker"].create(
            {
                "url": "/",
                "title": "Odoo",
            }
        )
        self.assertEqual(len(link_tracker.link_click_ids), 0)
        link = "/r/" + link_tracker.code

        self.url_open(
            link,
            headers={
                "User-Agent": "Mozilla/5.0 MicrosoftPreview/2.0 +https://aka.ms/MicrosoftPreview",
            },
            allow_redirects=False,
        )
        self.assertEqual(len(link_tracker.link_click_ids), 0)

        self.url_open(
            link,
            headers={
                "User-Agent": "Mozilla/5.0 Google-PageRenderer Google (+https://developers.google.com/+/web/snippet/)"
            },
            allow_redirects=False,
        )
        self.assertEqual(len(link_tracker.link_click_ids), 0)

        self.url_open(
            link,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
            },
            allow_redirects=False,
        )
        self.assertEqual(len(link_tracker.link_click_ids), 1)
