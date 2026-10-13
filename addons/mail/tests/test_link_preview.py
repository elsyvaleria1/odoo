import io
from types import SimpleNamespace
from unittest.mock import patch

import requests
from markupsafe import Markup
from requests.adapters import HTTPAdapter
from requests.utils import get_encoding_from_headers

import odoo.db
from odoo.exceptions import ConcurrencyError
from odoo.tests.common import tagged
from odoo.tests.transaction_case import _super_send

from odoo.addons.html_editor.tools import link_preview
from odoo.addons.mail.tests.common import MailCommon


@tagged("mail_link_preview", "mail_message", "post_install", "-at_install")
class TestLinkPreview(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.maxDiff = None
        cls.test_partner = cls.env["res.partner"].create({"name": "a partner"})
        cls.existing_message = cls.test_partner.message_post(body="Test")
        cls.title = "Test title"
        cls.og_title = "Le carousel ne démarre pas.webm"
        cls.og_description = "Test OG description"
        cls.og_image = "https://dummy-image-url.nothing"
        cls.source_url = "https://thisdomainedoentexist.nothing"

    def _patch_head_html(self, *args, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response.headers["Content-Type"] = "text/html"
        return response

    def _patched_get_html(self, content_type, content):
        response = requests.Response()
        response.status_code = 200
        response._content = content
        response.encoding = "utf-8"
        response.raw = io.BytesIO(response._content)
        response.headers["Content-Type"] = content_type
        return response

    def _patch_with_og_properties(self, *args, **kwargs):
        content = b"""
        <html>
        <head>
        <title>Test title</title>
        <meta property="og:title" content="Le carousel ne d\xc3\xa9marre pas.webm">
        <meta property="og:description" content="Test OG description">
        <meta property="og:image" content="https://dummy-image-url.nothing">
        </head>
        </html>
        """
        return self._patched_get_html("text/html", content)

    def _patch_without_og_properties(self, *args, **kwargs):
        content = b"""
        <html>
        <head>
        <title>Test title</title>
        </head>
        </html>
        """
        return self._patched_get_html("text/html", content)

    def _patch_with_image_mimetype(self, *args, **kwargs):
        content = b"""
        <html>
        <body>
        <img src='https://dummy-image-url.nothing'/>
        </body>
        </html>
        """
        return self._patched_get_html("image/png", content)

    def _patch_with_no_content_type(self, *args, **kwargs):
        content = b""""""
        return self._patched_get_html(None, content)

    def _patch_with_xml_declaration(self, *args, **kwargs):
        content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <html>
        <head>
        <title>Test title</title>
        </head>
        </html>
        """
        return self._patched_get_html("text/html", content)

    def _patch_utf8_without_charset_header(self, *args, **kwargs):
        content = (
            "<html><head><title>Réunion café à Montréal — décembre</title>"
            '<meta charset="utf-8">'
            '<meta property="og:title" content="Café ☕ déjà vu à Genève">'
            "</head></html>"
        ).encode()
        response = requests.Response()
        response.status_code = 200
        response._content = content
        response.raw = io.BytesIO(content)
        response.headers["Content-Type"] = "text/html"
        response.encoding = get_encoding_from_headers(response.headers)
        return response

    def test_a_preview_created_meanwhile_is_reused_not_duplicated(self):
        Preview = self.env["mail.link.preview"]
        existing = Preview.create({"source_url": "https://raced.example.com/"})
        previews = Preview._create_from_values_race_safe(
            [
                {"source_url": "https://raced.example.com/"},
                {"source_url": "https://fresh.example.com/"},
            ]
        )
        self.assertIn(existing, previews)
        self.assertEqual(len(previews), 2)

    def test_a_preview_committed_after_the_snapshot_asks_for_a_retry(self):
        url = "https://committed-elsewhere.example.com/"
        Preview = self.env["mail.link.preview"]
        Preview.search_count([])

        def delete_committed():
            with odoo.db.db_connect(self.env.cr.dbname).cursor() as cr:
                cr.execute("DELETE FROM mail_link_preview WHERE source_url = %s", [url])

        with odoo.db.db_connect(self.env.cr.dbname).cursor() as other:
            other.execute(
                "INSERT INTO mail_link_preview (source_url, create_date, write_date)"
                " VALUES (%s, now(), now())",
                [url],
            )
        self.addCleanup(delete_committed)
        with self.assertRaises(ConcurrencyError):
            Preview._create_from_values_race_safe([{"source_url": url}])

    def test_a_page_with_no_document_gives_no_preview(self):
        for body in (b"   ", b"<!-- nothing -->", b"<html><title></title></html>"):
            with self.subTest(body=body):
                response = requests.Response()
                response._content = body
                response._content_consumed = True
                response.status_code = 200
                response.headers["Content-Type"] = "text/html; charset=utf-8"
                self.assertIs(
                    link_preview.get_link_preview_from_html(self.source_url, response),
                    False,
                )

    def test_link_preview_utf8_without_charset_header(self):
        self.assertEqual(
            self._patch_utf8_without_charset_header().encoding,
            "ISO-8859-1",
            "precondition: requests defaults header-less text/html to latin-1",
        )
        session = link_preview.get_link_preview_session(self.env)
        with patch.object(
            requests.Session, "get", self._patch_utf8_without_charset_header
        ):
            preview = link_preview.get_link_preview_from_url(self.source_url, session)
        self.assertEqual(preview["og_title"], "Café ☕ déjà vu à Genève")

    def _through_the_adapter(self, respond):
        hops = []

        def send(adapter, request, **kwargs):
            hops.append((request.url, request.netguard_address))
            response = respond(request.url)
            response.request = request
            response.url = request.url
            return response

        def getaddrinfo(host, port, *args, **kwargs):
            return [(2, 1, 6, "", ("93.184.216.34", port))]

        session = link_preview.get_link_preview_session(self.env)
        with (
            patch("socket.getaddrinfo", side_effect=getaddrinfo),
            patch.object(requests.Session, "send", _super_send),
            patch.object(HTTPAdapter, "send", autospec=True, side_effect=send),
        ):
            preview = link_preview.get_link_preview_from_url(self.source_url, session)
        return preview, hops

    @staticmethod
    def _redirect(location):
        response = requests.Response()
        response.status_code = 302
        response.headers["location"] = location
        response.raw = io.BytesIO(b"")
        return response

    def test_link_preview_redirect_budget(self):
        preview, hops = self._through_the_adapter(
            lambda url: self._redirect(f"https://redir.nothing/{url.count('/')}")
        )
        self.assertFalse(preview)
        self.assertEqual(
            len(hops),
            link_preview.MAX_REDIRECTS + 1,
            "must stop after the redirect budget, not follow indefinitely",
        )

    def test_link_preview_relative_redirect(self):
        final_url = "https://thisdomainedoentexist.nothing/final"

        def respond(url):
            if url == final_url:
                return self._patch_without_og_properties()
            return self._redirect("/final")

        preview, hops = self._through_the_adapter(respond)
        self.assertEqual(preview["og_title"], self.title)
        self.assertEqual(
            hops,
            [(f"{self.source_url}/", "93.184.216.34"), (final_url, "93.184.216.34")],
            "relative Location must be urljoin'd, and every hop pinned",
        )

    def test_link_preview_refuses_a_non_public_destination(self):
        def getaddrinfo(host, port, *args, **kwargs):
            return [(2, 1, 6, "", ("169.254.169.254", port))]

        session = link_preview.get_link_preview_session(self.env)
        with (
            patch("socket.getaddrinfo", side_effect=getaddrinfo),
            patch.object(requests.Session, "send", _super_send),
            patch.object(HTTPAdapter, "send") as send,
        ):
            self.assertFalse(
                link_preview.get_link_preview_from_url(self.source_url, session)
            )
        send.assert_not_called()

    def test_link_preview_refuses_an_unguarded_session(self):
        with self.assertRaises(TypeError):
            link_preview.get_link_preview_from_url(self.source_url, requests.Session())

    def test_get_link_preview_from_url(self):
        test_cases = [
            (self._patch_with_og_properties, self.source_url),
            (self._patch_without_og_properties, self.source_url),
            (self._patch_with_image_mimetype, self.og_image),
            (self._patch_with_xml_declaration, self.source_url),
        ]
        expected_values = [
            {
                "og_description": self.og_description,
                "og_image": self.og_image,
                "og_mimetype": None,
                "og_title": self.og_title,
                "og_type": None,
                "og_site_name": None,
                "source_url": self.source_url,
            },
            {
                "og_description": None,
                "og_image": None,
                "og_mimetype": None,
                "og_title": self.title,
                "og_type": None,
                "og_site_name": None,
                "source_url": self.source_url,
            },
            {
                "image_mimetype": "image/png",
                "og_image": self.og_image,
                "source_url": self.og_image,
            },
            {
                "og_description": None,
                "og_image": None,
                "og_mimetype": None,
                "og_title": self.title,
                "og_type": None,
                "og_site_name": None,
                "source_url": self.source_url,
            },
        ]
        session = link_preview.get_link_preview_session(self.env)
        for (get_patch, url), expected in zip(
            test_cases, expected_values, strict=False
        ):
            with (
                self.subTest(get_patch=get_patch, url=url, expected=expected),
                patch.object(requests.Session, "get", get_patch),
            ):
                preview = link_preview.get_link_preview_from_url(url, session)
                self.assertEqual(preview, expected)

    def test_link_preview(self):
        with (
            patch.object(requests.Session, "get", self._patch_with_og_properties),
            patch.object(requests.Session, "head", self._patch_head_html),
        ):
            message = self.test_partner.message_post(
                body=Markup(f"<a href={self.source_url}>Nothing link</a>"),
            )

            def get_bus_params():
                return (
                    [(self.cr.dbname, "res.partner", self.env.user.partner_id.id)],
                    [
                        {
                            "type": "mail.record/insert",
                            "payload": {
                                "mail.link.preview": [
                                    {
                                        "id": message.message_link_preview_ids.link_preview_id.id,
                                        "image_mimetype": False,
                                        "og_description": self.og_description,
                                        "og_image": self.og_image,
                                        "og_mimetype": False,
                                        "og_site_name": False,
                                        "og_title": self.og_title,
                                        "og_type": False,
                                        "source_url": self.source_url,
                                    },
                                ],
                                "mail.message": self._filter_messages_fields(
                                    {
                                        "id": message.id,
                                        "message_link_preview_ids": message.message_link_preview_ids.ids,
                                    },
                                ),
                                "mail.message.link.preview": [
                                    {
                                        "id": message.message_link_preview_ids.id,
                                        "link_preview_id": message.message_link_preview_ids.link_preview_id.id,
                                        "message_id": message.id,
                                    }
                                ],
                            },
                        }
                    ],
                )

            with self.assertBus(get_params=get_bus_params):
                self.env["mail.link.preview"]._create_from_message_and_notify(message)

    def test_a_cached_preview_is_reused_when_the_url_set_changes_size_not(self):
        LP = self.env["mail.link.preview"]
        url_a, url_b = "https://cached.example.com/a", "https://cached.example.com/b"
        LP.create(
            [
                {"source_url": url_a, "og_title": "Cached A"},
                {"source_url": url_b, "og_title": "Cached B"},
            ]
        )
        LP.flush_model()
        fetched = []

        def _never_fetch(url, session=None):
            fetched.append(url)
            return {"source_url": url, "og_title": "REFETCHED"}

        message = (
            self.env["res.partner"]
            .create({"name": "preview"})
            .message_post(
                body=Markup(f'<p><a href="{url_a}">a</a></p>'),
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        )
        with patch(
            "odoo.addons.mail.models.mail_link_preview.get_link_preview_from_url",
            _never_fetch,
        ):
            LP._create_from_message_and_notify(message)
            self.assertEqual(fetched, [], "url_a is already cached")
            message.sudo().body = Markup(f'<p><a href="{url_b}">b</a></p>')
            message.flush_recordset()
            LP._create_from_message_and_notify(message)
        self.assertEqual(
            fetched, [], "url_b is cached too and must not be fetched over HTTP"
        )
        self.assertEqual(
            LP.search([("source_url", "=", url_b)]).og_title,
            "Cached B",
            "the cached row must survive, not be replaced by a refetch",
        )
        self.assertEqual(
            message.sudo().message_link_preview_ids.link_preview_id.source_url,
            url_b,
            "the message must end up pointing at the new url",
        )

    def test_link_preview_throttle_is_per_host(self):
        LP = self.env["mail.link.preview"]
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.link_preview_throttle", 1
        )
        LP.create(
            [
                {"source_url": "https://foo.com/page?ref=evil.com"},
                {"source_url": "https://notevil.com.attacker.net/x"},
            ]
        )
        LP.flush_model()
        self.assertFalse(
            LP._is_domain_throttled("https://evil.com/target"),
            "an unrelated substring match must not throttle a host with 0 previews",
        )
        LP.create(
            [
                {"source_url": "https://real.com/a"},
                {"source_url": "https://real.com/b"},
            ]
        )
        LP.flush_model()
        self.assertTrue(
            LP._is_domain_throttled("https://real.com/c"),
            "two recent previews of the same host exceed a throttle of 1",
        )

    def test_link_preview_no_content_type(self):
        with patch.object(
            requests.Session, "request", self._patch_with_no_content_type
        ):
            url = self.source_url
            session = link_preview.get_link_preview_session(self.env)
            link_preview.get_link_preview_from_url(url, session)

    def test_link_preview_ignore_internal_link(self):
        with (
            patch.object(requests.Session, "get", self._patch_with_og_properties),
            patch.object(requests.Session, "head", self._patch_head_html),
        ):
            urls = [
                ("http://localhost:8069/", "http://localhost:8069/odoo", 0),
                ("http://localhost:8069/", "http://localhost:8069/odoo/test", 0),
                ("http://localhost:8069/", "http://localhost:8069/web/test", 0),
                ("http://localhost:8069/", "http://localhost:8069/", 1),
                ("http://localhost:8069/", "http://localhost:8069/odoo-experience", 1),
                (
                    "http://localhost:8069/",
                    "http://localhost:8069/chat/5/bFtIfYHRco",
                    0,
                ),
                ("https://www.odoo.com/", "https://www.odoo.com/web", 0),
                ("https://www.odoo.com/", "https://www.odoo.com/odoo", 0),
                ("https://www.odoo.com/", "https://www.odoo.com/odoo/", 0),
                ("https://www.odoo.com/", "https://www.odoo.com/odoo?debug=assets", 0),
                ("https://www.odoo.com/", "https://www.odoo.com/odoo#anchor", 0),
                ("https://www.odoo.com/", "https://www.odoo.com/odoo-experience", 1),
                (
                    "https://www.odoo.com/",
                    "https://www.odoo.com/odoo/1519/tasks/4102866",
                    0,
                ),
                (
                    "http://www.odoo.com/",
                    "https://www.odoo.com/odoo/1519/tasks/4102866",
                    1,
                ),
                ("https://www.odoo.com/", "https://wwwaodoo.com/odoo/", 1),
                ("https://www.odoo.com/", "https://www.odoo.com/chat/", 0),
                ("https://www.odoo.com/", "https://www.odoo.com/chat/5/bFtIfYHRco", 0),
                ("http://www.odoo.com/", "https://www.odoo.com/chat/5/bFtIfYHRco", 1),
                (
                    "https://clients.odoo.com/",
                    "https://www.odoo.com/odoo/1519/tasks/4102866",
                    1,
                ),
                (
                    "https://clients.odoo.com/",
                    "https://www.odoo.com/chat/5/bFtIfYHRco",
                    1,
                ),
            ]
            for request_url, url, counter in urls:
                with self.subTest(request_url=request_url, url=url, counter=counter):
                    message = self.test_partner.message_post(
                        body=Markup(f'<a href="{url}">Nothing link</a>'),
                    )
                    self.env["mail.link.preview"]._create_from_message_and_notify(
                        message, request_url
                    )
                    link_preview_count = self.env[
                        "mail.message.link.preview"
                    ].search_count([("message_id", "=", message.id)])
                    self.assertEqual(link_preview_count, counter)

    def test_remove_unused_link_preview(self):
        with (
            patch.object(requests.Session, "get", self._patch_with_og_properties),
            patch.object(requests.Session, "head", self._patch_head_html),
        ):
            message = self.test_partner.message_post(
                body=Markup(
                    '<a href="https://www.odoo.com/odoo-experience">Nothing link</a> <a href="https://www.odoo.com/odoo-experience-2025">Other Nothing link</a>'
                ),
                message_type="comment",
            )
            self.env["mail.link.preview"]._create_from_message_and_notify(message)
            link_preview_count = self.env["mail.message.link.preview"].search_count(
                [("message_id", "=", message.id)]
            )
            self.assertEqual(link_preview_count, 2)
            self.test_partner._message_update_content(
                message,
                body=Markup(
                    '<a href="https://www.odoo.com/odoo-experience">Nothing link</a>'
                ),
            )
            self.env["mail.link.preview"]._create_from_message_and_notify(message)
            link_preview_count = self.env["mail.message.link.preview"].search_count(
                [("message_id", "=", message.id)]
            )
            self.assertEqual(link_preview_count, 1)

    def test_link_preview_throttle(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.link_preview_throttle", 1
        )
        with (
            patch.object(requests.Session, "get", self._patch_with_og_properties),
            patch.object(requests.Session, "head", self._patch_head_html),
        ):
            message = self.test_partner.message_post(
                body=Markup('<a href="%s">Nothing link</a>') % self.source_url,
            )
            self.env["mail.link.preview"]._create_from_message_and_notify(message)
            link_preview = (
                self.env["mail.message.link.preview"]
                .search([("message_id", "=", message.id)])
                .link_preview_id
            )
            message = self.test_partner.message_post(
                body=Markup('<a href="%s/test">Nothing link</a>') % self.source_url
            )
            self.env["mail.link.preview"]._create_from_message_and_notify(message)
            link_preview_count = self.env["mail.message.link.preview"].search_count(
                [("link_preview_id", "=", link_preview.id)]
            )
            self.assertEqual(link_preview_count, 1)

    def test_link_preview_delete_with_message(self):
        with (
            patch.object(requests.Session, "get", self._patch_with_og_properties),
            patch.object(requests.Session, "head", self._patch_head_html),
        ):
            message = self.test_partner.message_post(
                body=Markup('<a href="%s">Test link</a>') % self.source_url,
                message_type="comment",
            )
            self.env["mail.link.preview"]._create_from_message_and_notify(message)
            preview = message.message_link_preview_ids
            self.assertTrue(preview)
            self.assertEqual(preview.link_preview_id.source_url, self.source_url)
            self.test_partner._message_update_content(message, body="")
            self.assertFalse(message.message_link_preview_ids)

    def test_an_author_who_reads_no_preview_empties_their_message(self):
        with (
            patch.object(requests.Session, "get", self._patch_with_og_properties),
            patch.object(requests.Session, "head", self._patch_head_html),
        ):
            partner = self.test_partner.with_user(self.user_employee)
            message = partner.message_post(
                body=Markup('<a href="%s">Test link</a>') % self.source_url,
                message_type="comment",
            )
            self.env["mail.link.preview"]._create_from_message_and_notify(message)
        previews = message.sudo().message_link_preview_ids
        self.assertTrue(previews)
        self.assertFalse(
            self.env["mail.message.link.preview"]
            .with_user(self.user_employee)
            .has_access("read")
        )

        partner._message_update_content(message, body="")

        self.assertFalse(previews.exists())

    def test_the_cleaning_privilege_reaches_no_preview_of_a_message_with_a_file(self):
        with (
            patch.object(requests.Session, "get", self._patch_with_og_properties),
            patch.object(requests.Session, "head", self._patch_head_html),
        ):
            message = self.test_partner.message_post(
                body=Markup('<a href="%s">Test link</a>') % self.source_url,
                message_type="comment",
                attachments=[("kept.txt", b"kept")],
            )
            self.env["mail.link.preview"]._create_from_message_and_notify(message)
        previews = (
            self.env["mail.message.link.preview"]
            .with_user(self.user_employee)
            .with_privilege("mail.privilege_clean_emptied_message")
        )

        self.assertFalse(previews.search([("message_id", "=", message.id)]))


@tagged("mail_link_preview", "mail_message", "post_install", "-at_install")
class TestLinkPreviewFetchBudget(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_partner = cls.env["res.partner"].create({"name": "budget partner"})

    def setUp(self):
        super().setUp()
        link_preview.forget_failed_fetches()
        self.addCleanup(link_preview.forget_failed_fetches)
        self.fetched = []

    def _post_links(self, urls):
        return self.test_partner.message_post(
            body=Markup("").join(
                Markup('<a href="%s">link</a> ') % url for url in urls
            ),
            message_type="comment",
        )

    def _failing_fetch(self, url, session=None):
        self.fetched.append(url)
        return False

    def _create_previews(self, message, fetch):
        with patch(
            "odoo.addons.mail.models.mail_link_preview.get_link_preview_from_url",
            fetch,
        ):
            self.env["mail.link.preview"]._create_from_message_and_notify(message)

    def test_dead_links_do_not_each_cost_a_fetch(self):
        message = self._post_links(
            [f"https://dead-{index}.example.com/" for index in range(200)]
        )
        self._create_previews(message, self._failing_fetch)
        self.assertLessEqual(
            len(self.fetched),
            10,
            "a message of dead links must not hold the worker for a fetch per link",
        )
        self.assertFalse(message.message_link_preview_ids)

    def test_slow_links_stop_at_the_request_time_budget(self):
        clock = [1000.0]

        def slow_fetch(url, session=None):
            self.fetched.append(url)
            clock[0] += 9
            return False

        message = self._post_links(
            [f"https://slow-{index}.example.com/" for index in range(20)]
        )
        with patch(
            "odoo.addons.mail.models.mail_link_preview.time",
            SimpleNamespace(monotonic=lambda: clock[0]),
            create=True,
        ):
            self._create_previews(message, slow_fetch)
        self.assertLessEqual(
            len(self.fetched),
            2,
            "fetches that each take 9 s must stop once the budget is spent",
        )

    def test_failed_fetches_count_toward_the_host_throttle(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.link_preview_throttle", 1
        )
        message = self._post_links(
            [f"https://flaky.example.com/{index}" for index in range(6)]
        )
        self._create_previews(message, self._failing_fetch)
        self.assertEqual(
            len(self.fetched),
            2,
            "a host that keeps failing is throttled like one that keeps answering",
        )
        self.assertTrue(
            self.env["mail.link.preview"]._is_domain_throttled(
                "https://flaky.example.com/next"
            )
        )

    def test_a_working_message_still_gets_its_five_previews(self):
        def fetch(url, session=None):
            self.fetched.append(url)
            return {"source_url": url, "og_title": url}

        message = self._post_links(
            [f"https://ok-{index}.example.com/" for index in range(7)]
        )
        self._create_previews(message, fetch)
        self.assertEqual(len(self.fetched), 5)
        self.assertEqual(len(message.message_link_preview_ids), 5)
