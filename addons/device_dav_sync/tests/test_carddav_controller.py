import base64

from lxml import etree

from odoo import Command
from odoo.tests.common import tagged

from .test_dav_authentication import dav_key
from odoo.addons.device.tests.common import DeviceHttpCase


@tagged("post_install", "-at_install")
class TestCardDAVController(DeviceHttpCase):
    def setUp(self):
        super().setUp()

        self.test_user = self.env["res.users"].create(
            {
                "name": "Test DAV User",
                "login": "test_carddav_user",
                "email": "test@example.com",
                "group_ids": [
                    (4, self.env.ref("base.group_user").id),
                    (4, self.env.ref("base.group_partner_manager").id),
                ],
            }
        )
        self.test_user.write({"password": "test_password_123"})
        self.dav_key = dav_key(self.test_user)

        self.device_profile = self.env["device.profile"].create(
            {
                "name": "Test Remote Config",
                "dav_enabled": True,
                "dav_addressbook_enabled": True,
            }
        )

        self.test_device = self.env["device.device"].create(
            {
                "name": "Test CardDAV Device",
                "identifier": "test_carddav_device_001",
                "config_id": self.device_profile.id,
                "device_category_id": self.env.ref(
                    "device_dav_sync.device_category_dav_client"
                ).id,
                "dav_sync_enabled": True,
                "dav_user_id": self.test_user.id,
                "dav_addressbook_enabled": True,
            }
        )
        self.auth_token = self.test_device.sudo().credential_id.credential_value

        self.addressbook = self.env["dav.addressbook"].create(
            {
                "name": "Test Addressbook",
                "user_id": self.test_user.id,
            }
        )

        self.contact1 = self.env["res.partner"].create(
            {
                "name": "Alice Smith",
                "email": "alice@example.com",
                "phone_ids": [
                    Command.create({"number": "+1-555-0101", "type": "landline"})
                ],
                "user_id": self.test_user.id,
            }
        )
        self.contact2 = self.env["res.partner"].create(
            {
                "name": "Bob Jones",
                "email": "bob@example.com",
                "phone_ids": [
                    Command.create({"number": "+1-555-0201", "type": "landline"})
                ],
                "user_id": self.test_user.id,
            }
        )

        self.addressbook_home_url = f"/dav/addressbooks/{self.test_user.login}"
        self.addressbook_url = f"{self.addressbook_home_url}/{self.addressbook.id}"
        self.contact1_url = f"{self.addressbook_url}/{self.contact1.id}.vcf"

    def _get_auth_headers(self, use_bearer=True):
        if use_bearer:
            return {"Authorization": f"Bearer {self.auth_token}"}
        credentials = f"{self.test_user.login}:{self.dav_key}"
        b64_credentials = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {b64_credentials}"}

    def test_propfind_addressbook_home(self):
        headers = self._get_auth_headers()
        headers["Depth"] = "1"
        headers["Content-Type"] = "application/xml; charset=utf-8"

        propfind_body = """<?xml version="1.0" encoding="utf-8"?>
        <D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
            <D:prop>
                <D:resourcetype/>
                <D:displayname/>
            </D:prop>
        </D:propfind>"""

        response = self.url_open(
            self.addressbook_home_url,
            data=propfind_body.encode(),
            headers=headers,
            method="PROPFIND",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        self.assertIn("multistatus", root.tag.lower())
        responses = root.findall(".//{DAV:}response")
        self.assertGreaterEqual(len(responses), 2)

    def test_propfind_addressbook_collection(self):
        headers = self._get_auth_headers()
        headers["Depth"] = "1"
        headers["Content-Type"] = "application/xml; charset=utf-8"

        propfind_body = """<?xml version="1.0" encoding="utf-8"?>
        <D:propfind xmlns:D="DAV:">
            <D:prop>
                <D:resourcetype/>
                <D:getetag/>
                <D:getcontenttype/>
            </D:prop>
        </D:propfind>"""

        response = self.url_open(
            self.addressbook_url,
            data=propfind_body.encode(),
            headers=headers,
            method="PROPFIND",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        responses = root.findall(".//{DAV:}response")
        self.assertGreaterEqual(len(responses), 3)

    def test_get_vcard(self):
        response = self.url_open(self.contact1_url, headers=self._get_auth_headers())

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/vcard", response.headers.get("Content-Type", "").lower())

        vcard_data = response.content.decode()
        self.assertIn("BEGIN:VCARD", vcard_data)
        self.assertIn("END:VCARD", vcard_data)
        self.assertIn("Alice Smith", vcard_data)
        self.assertIn("alice@example.com", vcard_data)
        self.assertIn("ETag", response.headers)

    def test_put_vcard_create(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "text/vcard; charset=utf-8"
        headers["If-None-Match"] = "*"

        vcard_data = (
            "BEGIN:VCARD\r\n"
            "VERSION:4.0\r\n"
            "FN:Charlie Brown\r\n"
            "N:Brown;Charlie;;;\r\n"
            "EMAIL:charlie@example.com\r\n"
            "TEL;TYPE=work:+1-555-0303\r\n"
            "END:VCARD\r\n"
        )
        new_contact_url = f"{self.addressbook_url}/new-contact.vcf"

        response = self.url_open(
            new_contact_url,
            data=vcard_data.encode(),
            headers=headers,
            method="PUT",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("ETag", response.headers)
        created = self.env["res.partner"].search(
            [("email", "=", "charlie@example.com")]
        )
        self.assertEqual(len(created), 1)
        may_assign = created.with_user(self.test_user)._has_field_access(
            created._fields["user_id"], "write"
        )
        self.assertEqual(
            created.user_id, self.test_user if may_assign else self.env["res.users"]
        )

    def test_put_vcard_update(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "text/vcard; charset=utf-8"

        vcard_data = (
            "BEGIN:VCARD\r\n"
            "VERSION:4.0\r\n"
            "FN:Alice Smith\r\n"
            "N:Smith;Alice;;;\r\n"
            "EMAIL:alice.updated@example.com\r\n"
            "TEL;TYPE=work:+1-555-0102\r\n"
            "END:VCARD\r\n"
        )

        response = self.url_open(
            self.contact1_url,
            data=vcard_data.encode(),
            headers=headers,
            method="PUT",
        )

        self.assertEqual(response.status_code, 204)
        self.contact1.invalidate_recordset(["email"])
        self.assertEqual(self.contact1.email, "alice.updated@example.com")

    def test_delete_vcard(self):
        temp_contact = self.env["res.partner"].create(
            {
                "name": "Delete Me",
                "email": "delete@example.com",
                "user_id": self.test_user.id,
            }
        )
        temp_contact_url = f"{self.addressbook_url}/{temp_contact.id}.vcf"

        response = self.url_open(
            temp_contact_url,
            headers=self._get_auth_headers(),
            method="DELETE",
        )

        self.assertEqual(response.status_code, 204)
        temp_contact.invalidate_recordset(["active"])
        self.assertTrue(temp_contact.exists())
        self.assertFalse(temp_contact.active)

    def test_report_addressbook_query(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/xml; charset=utf-8"
        headers["Depth"] = "1"

        report_body = """<?xml version="1.0" encoding="utf-8"?>
        <C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
            <D:prop>
                <D:getetag/>
                <C:address-data/>
            </D:prop>
            <C:filter>
                <C:prop-filter name="EMAIL">
                    <C:text-match>example.com</C:text-match>
                </C:prop-filter>
            </C:filter>
        </C:addressbook-query>"""

        response = self.url_open(
            self.addressbook_url,
            data=report_body.encode(),
            headers=headers,
            method="REPORT",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        self.assertGreater(len(root.findall(".//{DAV:}response")), 0)
        self.assertTrue(root.findall(".//{urn:ietf:params:xml:ns:carddav}address-data"))

    def test_report_multiget(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/xml; charset=utf-8"

        report_body = f"""<?xml version="1.0" encoding="utf-8"?>
        <C:addressbook-multiget xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
            <D:prop>
                <D:getetag/>
                <C:address-data/>
            </D:prop>
            <D:href>{self.contact1_url}</D:href>
        </C:addressbook-multiget>"""

        response = self.url_open(
            self.addressbook_url,
            data=report_body.encode(),
            headers=headers,
            method="REPORT",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        self.assertEqual(len(root.findall(".//{DAV:}response")), 1)

    def test_report_sync_collection(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/xml; charset=utf-8"

        sync_body = """<?xml version="1.0" encoding="utf-8"?>
        <D:sync-collection xmlns:D="DAV:">
            <D:sync-token/>
            <D:sync-level>1</D:sync-level>
            <D:prop>
                <D:getetag/>
            </D:prop>
        </D:sync-collection>"""

        response = self.url_open(
            self.addressbook_url,
            data=sync_body.encode(),
            headers=headers,
            method="REPORT",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        sync_token_elem = root.find(".//{DAV:}sync-token")
        self.assertIsNotNone(sync_token_elem)
        self.assertTrue(sync_token_elem.text)

        sync_body_with_token = f"""<?xml version="1.0" encoding="utf-8"?>
        <D:sync-collection xmlns:D="DAV:">
            <D:sync-token>{sync_token_elem.text}</D:sync-token>
            <D:sync-level>1</D:sync-level>
            <D:prop>
                <D:getetag/>
            </D:prop>
        </D:sync-collection>"""

        response2 = self.url_open(
            self.addressbook_url,
            data=sync_body_with_token.encode(),
            headers=headers,
            method="REPORT",
        )
        self.assertEqual(response2.status_code, 207)

    def test_basic_auth(self):
        headers = self._get_auth_headers(use_bearer=False)
        headers["Depth"] = "0"

        response = self.url_open(
            self.addressbook_home_url,
            headers=headers,
            method="PROPFIND",
        )
        self.assertNotEqual(response.status_code, 401)

    def test_unauthorized_access(self):
        response = self.url_open(self.addressbook_home_url, method="PROPFIND")

        self.assertEqual(response.status_code, 401)
        self.assertIn("WWW-Authenticate", response.headers)

    def test_provision_default_addressbooks(self):
        other_user = self.env["res.users"].create(
            {"name": "Fresh Rep", "login": "fresh_rep_dav"}
        )
        self.env["device.device"].create(
            {
                "name": "Fresh Device",
                "identifier": "fresh_dav_device",
                "config_id": self.device_profile.id,
                "device_category_id": self.env.ref(
                    "device_dav_sync.device_category_dav_client"
                ).id,
                "dav_sync_enabled": True,
                "dav_user_id": other_user.id,
            }
        )
        self.assertFalse(
            self.env["dav.addressbook"].search([("user_id", "=", other_user.id)])
        )

        self.env["dav.addressbook"]._provision_default_addressbooks(other_user)

        books = self.env["dav.addressbook"].search([("user_id", "=", other_user.id)])
        self.assertTrue(books)
        self.assertIn("My Contacts", books.mapped("name"))

    def test_put_vcard_with_mobile_number(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "text/vcard; charset=utf-8"
        headers["If-None-Match"] = "*"

        vcard_data = (
            "BEGIN:VCARD\r\n"
            "VERSION:4.0\r\n"
            "FN:Cell Owner\r\n"
            "N:Owner;Cell;;;\r\n"
            "EMAIL:cell@example.com\r\n"
            "TEL;TYPE=CELL:+1-555-9000\r\n"
            "END:VCARD\r\n"
        )
        response = self.url_open(
            f"{self.addressbook_url}/cell-owner.vcf",
            data=vcard_data.encode(),
            headers=headers,
            method="PUT",
        )

        self.assertEqual(response.status_code, 201)
        created = self.env["res.partner"].search([("email", "=", "cell@example.com")])
        self.assertEqual(len(created), 1)
        mobile = created._phone_get_number("mobile")
        self.assertEqual(mobile.type, "mobile")
        self.assertEqual(mobile.sanitized, "+15559000")

    def test_get_records_sync_state(self):
        self.env["dav.sync.state"].search(
            [("device_id", "=", self.test_device.id)]
        ).unlink()

        response = self.url_open(self.contact1_url, headers=self._get_auth_headers())
        self.assertEqual(response.status_code, 200)

        state = self.env["dav.sync.state"].search(
            [
                ("device_id", "=", self.test_device.id),
                ("resource_model", "=", "res.partner"),
                ("resource_id", "=", self.contact1.id),
            ]
        )
        self.assertEqual(len(state), 1)
        self.assertEqual(state.sync_status, "synced")
        self.assertEqual(state.resource_type, "contact")

    def test_sync_collection_reports_deletion(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/xml; charset=utf-8"

        initial = self.url_open(
            self.addressbook_url,
            data=(
                b'<?xml version="1.0" encoding="utf-8"?>'
                b'<D:sync-collection xmlns:D="DAV:"><D:sync-token/>'
                b"<D:sync-level>1</D:sync-level>"
                b"<D:prop><D:getetag/></D:prop></D:sync-collection>"
            ),
            headers=headers,
            method="REPORT",
        )
        token = etree.fromstring(initial.content).find(".//{DAV:}sync-token").text

        self.contact2.action_archive()
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE res_partner SET write_date = write_date + interval '10 seconds'"
            " WHERE id = %s",
            [self.contact2.id],
        )
        self.env["res.partner"].invalidate_model(["write_date"])

        followup = self.url_open(
            self.addressbook_url,
            data=(
                f'<?xml version="1.0" encoding="utf-8"?>'
                f'<D:sync-collection xmlns:D="DAV:"><D:sync-token>{token}</D:sync-token>'
                f"<D:sync-level>1</D:sync-level>"
                f"<D:prop><D:getetag/></D:prop></D:sync-collection>"
            ).encode(),
            headers=headers,
            method="REPORT",
        )
        self.assertEqual(followup.status_code, 207)
        root = etree.fromstring(followup.content)
        hrefs = {
            r.find(".//{DAV:}href").text: r for r in root.findall(".//{DAV:}response")
        }
        archived_url = f"{self.addressbook_url}/{self.contact2.id}.vcf"
        self.assertIn(archived_url, hrefs, "deletion must be relayed to the fleet")
        status = hrefs[archived_url].find(".//{DAV:}status")
        self.assertIn("404", status.text)

    def test_put_conflict_server_wins(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "text/vcard; charset=utf-8"
        headers["If-Match"] = '"deadbeefstale"'

        vcard_data = (
            "BEGIN:VCARD\r\nVERSION:4.0\r\nFN:Alice Smith\r\n"
            "EMAIL:should-not-apply@example.com\r\nEND:VCARD\r\n"
        )
        response = self.url_open(
            self.contact1_url,
            data=vcard_data.encode(),
            headers=headers,
            method="PUT",
        )
        self.assertEqual(response.status_code, 412)
        self.contact1.invalidate_recordset(["email"])
        self.assertEqual(self.contact1.email, "alice@example.com")

    def test_put_conflict_client_wins(self):
        device = self.env["device.device"].browse(self.test_device.id)
        state = self.env["dav.sync.state"].get_or_create_sync_state(
            device, "contact", "res.partner", self.contact1.id
        )
        state.conflict_resolution_strategy = "client_wins"

        headers = self._get_auth_headers()
        headers["Content-Type"] = "text/vcard; charset=utf-8"
        headers["If-Match"] = '"deadbeefstale"'
        vcard_data = (
            "BEGIN:VCARD\r\nVERSION:4.0\r\nFN:Alice Smith\r\n"
            "EMAIL:client-wins@example.com\r\nEND:VCARD\r\n"
        )
        response = self.url_open(
            self.contact1_url,
            data=vcard_data.encode(),
            headers=headers,
            method="PUT",
        )
        self.assertEqual(response.status_code, 204)
        self.contact1.invalidate_recordset(["email"])
        self.assertEqual(self.contact1.email, "client-wins@example.com")

    def test_carddav_disabled_returns_404(self):
        self.device_profile.dav_addressbook_enabled = False
        response = self.url_open(
            self.addressbook_home_url,
            headers=self._get_auth_headers(),
            method="PROPFIND",
        )
        self.assertEqual(response.status_code, 404)

    def test_report_xxe_local_file_entity_rejected(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/xml; charset=utf-8"
        xxe_body = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<!DOCTYPE C:addressbook-query [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b'<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">'
            b"<D:prop><D:getetag/><C:address-data>&xxe;</C:address-data></D:prop>"
            b"</C:addressbook-query>"
        )
        response = self.url_open(
            self.addressbook_url,
            data=xxe_body,
            headers=headers,
            method="REPORT",
        )
        self.assertNotIn(b"root:", response.content)

    def test_propfind_xxe_entity_rejected(self):
        headers = self._get_auth_headers()
        headers["Depth"] = "1"
        headers["Content-Type"] = "application/xml; charset=utf-8"
        xxe_body = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<!DOCTYPE D:propfind [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b'<D:propfind xmlns:D="DAV:"><D:prop><D:displayname>&xxe;</D:displayname>'
            b"</D:prop></D:propfind>"
        )
        response = self.url_open(
            self.addressbook_home_url,
            data=xxe_body,
            headers=headers,
            method="PROPFIND",
        )
        self.assertNotIn(b"root:", response.content)

    def test_report_normal_request_still_parses(self):
        response = self.url_open(self.contact1_url, headers=self._get_auth_headers())
        self.assertEqual(response.status_code, 200)
        self.assertIn("BEGIN:VCARD", response.content.decode())

    def test_device_carddav_optout_returns_404(self):
        self.test_device.dav_addressbook_enabled = False
        response = self.url_open(
            self.addressbook_home_url,
            headers=self._get_auth_headers(),
            method="PROPFIND",
        )
        self.assertEqual(response.status_code, 404)

    def test_disabled_sync_device_revokes_access_and_is_not_duplicated(self):
        self.test_device.dav_sync_enabled = False
        headers = self._get_auth_headers(use_bearer=False)
        headers["Depth"] = "0"
        response = self.url_open(
            self.addressbook_home_url,
            headers=headers,
            method="PROPFIND",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self.env["device.device"].search_count(
                [("dav_user_id", "=", self.test_user.id)]
            ),
            1,
        )
