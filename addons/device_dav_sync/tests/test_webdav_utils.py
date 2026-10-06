from datetime import UTC, datetime, timedelta, timezone

from lxml import etree

from odoo.exceptions import ValidationError
from odoo.tests import BaseCase

from ..lib.webdav_utils import (
    NS_DAV,
    get_sync_timestamp,
    prepare_etag,
    prepare_href_property,
    prepare_multistatus_response,
    safe_parse_xml,
    store_dav_record,
)
from odoo.addons.device.tests.common import DeviceTransactionCase


class TestSafeParseXml(DeviceTransactionCase):
    def test_local_file_entity_not_resolved(self):
        payload = (
            b'<?xml version="1.0"?>'
            b'<!DOCTYPE root [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b"<root>&xxe;</root>"
        )
        root = safe_parse_xml(payload)
        serialized = etree.tostring(root)
        self.assertIn(b"&xxe;", serialized)
        self.assertNotIn(b"root:", serialized)

    def test_ssrf_url_entity_not_resolved(self):
        payload = (
            b'<?xml version="1.0"?>'
            b'<!DOCTYPE root [<!ENTITY xxe SYSTEM "http://169.254.169.254/latest/meta-data/">]>'
            b"<root>&xxe;</root>"
        )
        root = safe_parse_xml(payload)
        serialized = etree.tostring(root)
        self.assertIn(b"&xxe;", serialized)

    def test_normal_xml_still_parses(self):
        payload = b'<?xml version="1.0"?><root><child>value</child></root>'
        root = safe_parse_xml(payload)
        self.assertEqual(root.find("child").text, "value")

    def test_malformed_xml_raises_syntax_error(self):
        with self.assertRaises(etree.XMLSyntaxError):
            safe_parse_xml(b"<root><unclosed></root>")


class TestStoreDavRecord(DeviceTransactionCase):
    def test_success_returns_the_record(self):
        partner = store_dav_record(
            self.env,
            lambda: self.env["res.partner"].create({"name": "Kept"}),
        )
        self.assertEqual(partner.name, "Kept")

    def test_validation_error_becomes_valueerror(self):
        def store():
            raise ValidationError("stop before start")

        with self.assertRaises(ValueError):
            store_dav_record(self.env, store)

    def test_integrity_error_becomes_valueerror(self):
        with self.assertRaises(ValueError):
            store_dav_record(
                self.env,
                lambda: self.env["calendar.event"].create({"name": False}),
            )

    def test_the_transaction_survives_a_rejection(self):
        with self.assertRaises(ValueError):
            store_dav_record(
                self.env,
                lambda: self.env["calendar.event"].create({"name": False}),
            )
        self.assertIsInstance(self.env["res.partner"].search_count([]), int)


class TestDavWireValues(BaseCase):
    def test_etag_values(self):
        for value, expected in (
            (None, '""'),
            (False, '""'),
            ("", '""'),
            ("abc", '"abc"'),
            ('"abc"', '"abc"'),
            ('"abc', '"abc'),
        ):
            with self.subTest(value=value):
                self.assertEqual(prepare_etag(value), expected)

    def test_sync_timestamp_uses_utc_wall_time_and_truncates(self):
        for value, expected in (
            (None, 0),
            (False, 0),
            (datetime(1970, 1, 1), 0),
            (datetime(1970, 1, 1, 0, 0, 1, 999999), 1),
            (datetime(1969, 12, 31, 23, 59, 59, 500000), 0),
            (datetime(1970, 1, 1, tzinfo=UTC), 0),
            (datetime(1970, 1, 1, tzinfo=timezone(timedelta(hours=-6))), 0),
        ):
            with self.subTest(value=value):
                self.assertEqual(get_sync_timestamp(value), expected)

    def test_href_property_is_fresh_and_escapes_text(self):
        for url in (None, "", "/dav/á?x=1&y=<two>"):
            with self.subTest(url=url):
                first = prepare_href_property(url)
                second = prepare_href_property(url)
                self.assertIsNot(first, second)
                self.assertEqual(first.tag, "wrapper")
                self.assertEqual(len(first), 1)
                self.assertEqual(first[0].tag, f"{{{NS_DAV}}}href")
                self.assertEqual(first[0].text, url)
                parsed = etree.fromstring(etree.tostring(first))
                self.assertEqual(parsed[0].text or "", url or "")

    def test_multistatus_retags_the_property_wrapper(self):
        prop = f"{{{NS_DAV}}}current-user-principal"
        wrapper = prepare_href_property("/dav/principals/users/a&b/")
        response = prepare_multistatus_response(
            [{"href": "/dav/", "props": {prop: wrapper}}]
        )
        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.get_data())
        element = root.find(f".//{prop}")
        self.assertIsNotNone(element)
        self.assertEqual(element[0].tag, f"{{{NS_DAV}}}href")
        self.assertEqual(element[0].text, "/dav/principals/users/a&b/")
        self.assertEqual(wrapper.tag, prop)
        self.assertIsNone(root.find(".//wrapper"))

    def test_invalid_href_xml_text_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare_href_property("/dav/\x00")
