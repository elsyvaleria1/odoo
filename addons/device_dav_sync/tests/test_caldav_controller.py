import base64
from datetime import datetime, timedelta

from lxml import etree

from odoo.tests.common import tagged

from .test_dav_authentication import dav_key
from odoo.addons.device.tests.common import DeviceHttpCase

NS_APPLE_ICAL = "http://apple.com/ns/ical/"


@tagged("post_install", "-at_install")
class TestCalDAVController(DeviceHttpCase):
    def setUp(self):
        super().setUp()

        self.test_user = self.env["res.users"].create(
            {
                "name": "Test CalDAV User",
                "login": "test_caldav_user",
                "email": "caldav@example.com",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        self.test_user.write({"password": "test_password_456"})
        self.dav_key = dav_key(self.test_user)

        self.device_profile = self.env["device.profile"].create(
            {
                "name": "Test Remote Config",
                "dav_enabled": True,
                "dav_calendar_enabled": True,
            }
        )

        self.test_device = self.env["device.device"].create(
            {
                "name": "Test CalDAV Device",
                "identifier": "test_caldav_device_001",
                "config_id": self.device_profile.id,
                "device_category_id": self.env.ref(
                    "device_dav_sync.device_category_dav_client"
                ).id,
                "dav_sync_enabled": True,
                "dav_user_id": self.test_user.id,
                "dav_calendar_enabled": True,
            }
        )
        self.auth_token = self.test_device.sudo().credential_id.credential_value

        self.calendar = self.env["dav.calendar"].create(
            {
                "name": "Test Calendar",
                "user_id": self.test_user.id,
                "color": "#FF5733",
            }
        )

        now = datetime.now()
        self.event1 = self.env["calendar.event"].create(
            {
                "name": "Team Meeting",
                "start": now + timedelta(days=1),
                "stop": now + timedelta(days=1, hours=1),
                "user_id": self.test_user.id,
                "description": "Discuss project status",
            }
        )
        self.event2 = self.env["calendar.event"].create(
            {
                "name": "Client Call",
                "start": now + timedelta(days=2),
                "stop": now + timedelta(days=2, hours=2),
                "user_id": self.test_user.id,
                "location": "Conference Room A",
            }
        )

        self.calendar_home_url = f"/dav/calendars/{self.test_user.login}"
        self.calendar_url = f"{self.calendar_home_url}/{self.calendar.id}"
        self.event1_url = f"{self.calendar_url}/{self.event1.id}.ics"

    def _get_auth_headers(self, use_bearer=True):
        if use_bearer:
            return {"Authorization": f"Bearer {self.auth_token}"}
        credentials = f"{self.test_user.login}:{self.dav_key}"
        b64_credentials = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {b64_credentials}"}

    def _bump_write_date(self, events, seconds=10):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE calendar_event"
            " SET write_date = write_date + (%s || ' seconds')::interval"
            " WHERE id = ANY(%s)",
            [str(seconds), events.ids],
        )
        self.env["calendar.event"].invalidate_model(["write_date"])

    def test_propfind_calendar_home(self):
        headers = self._get_auth_headers()
        headers["Depth"] = "1"
        headers["Content-Type"] = "application/xml; charset=utf-8"

        propfind_body = """<?xml version="1.0" encoding="utf-8"?>
        <D:propfind xmlns:D="DAV:" xmlns:CAL="urn:ietf:params:xml:ns:caldav">
            <D:prop>
                <D:resourcetype/>
                <D:displayname/>
                <D:getctag/>
            </D:prop>
        </D:propfind>"""

        response = self.url_open(
            self.calendar_home_url,
            data=propfind_body.encode(),
            headers=headers,
            method="PROPFIND",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        self.assertIn("multistatus", root.tag.lower())
        responses = root.findall(".//{DAV:}response")
        self.assertGreaterEqual(len(responses), 2)

    def test_propfind_calendar_collection(self):
        headers = self._get_auth_headers()
        headers["Depth"] = "1"
        headers["Content-Type"] = "application/xml; charset=utf-8"

        propfind_body = """<?xml version="1.0" encoding="utf-8"?>
        <D:propfind xmlns:D="DAV:" xmlns:CAL="urn:ietf:params:xml:ns:caldav">
            <D:prop>
                <D:resourcetype/>
                <D:getetag/>
                <D:getcontenttype/>
                <CAL:supported-calendar-component-set/>
            </D:prop>
        </D:propfind>"""

        response = self.url_open(
            self.calendar_url,
            data=propfind_body.encode(),
            headers=headers,
            method="PROPFIND",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        responses = root.findall(".//{DAV:}response")
        self.assertGreaterEqual(len(responses), 3)

    def test_calendar_color_property(self):
        headers = self._get_auth_headers()
        headers["Depth"] = "0"
        headers["Content-Type"] = "application/xml; charset=utf-8"

        propfind_body = f"""<?xml version="1.0" encoding="utf-8"?>
        <D:propfind xmlns:D="DAV:" xmlns:ICAL="{NS_APPLE_ICAL}">
            <D:prop>
                <ICAL:calendar-color/>
            </D:prop>
        </D:propfind>"""

        response = self.url_open(
            self.calendar_url,
            data=propfind_body.encode(),
            headers=headers,
            method="PROPFIND",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        colors = root.findall(f".//{{{NS_APPLE_ICAL}}}calendar-color")
        self.assertTrue(colors)
        self.assertEqual(colors[0].text, "#FF5733")

    def test_get_icalendar(self):
        response = self.url_open(self.event1_url, headers=self._get_auth_headers())

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/calendar", response.headers.get("Content-Type", "").lower())

        ical_data = response.content.decode()
        self.assertIn("BEGIN:VCALENDAR", ical_data)
        self.assertIn("BEGIN:VEVENT", ical_data)
        self.assertIn("END:VEVENT", ical_data)
        self.assertIn("END:VCALENDAR", ical_data)
        self.assertIn("Team Meeting", ical_data)
        self.assertIn("ETag", response.headers)

    def test_put_icalendar_create(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "text/calendar; charset=utf-8"
        headers["If-None-Match"] = "*"

        start_dt = datetime.now() + timedelta(days=5)
        end_dt = start_dt + timedelta(hours=1)
        ical_data = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Odoo//Test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:test-event-new-123@example.com\r\n"
            f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            "SUMMARY:New Test Event\r\n"
            "DESCRIPTION:This is a test event created via PUT\r\n"
            "LOCATION:Test Location\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        new_event_url = f"{self.calendar_url}/test-event-new-123@example.com.ics"

        response = self.url_open(
            new_event_url,
            data=ical_data.encode(),
            headers=headers,
            method="PUT",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("ETag", response.headers)
        created = self.env["calendar.event"].search(
            [("ical_uid", "=", "test-event-new-123@example.com")]
        )
        self.assertEqual(len(created), 1)
        self.assertEqual(created.name, "New Test Event")
        self.assertEqual(created.user_id, self.test_user)

    def test_put_malformed_icalendar_is_400_not_500(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "text/calendar; charset=utf-8"
        headers["If-None-Match"] = "*"

        end_before_start = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:bad-range@example.com\r\n"
            "SUMMARY:Backwards\r\n"
            "DTSTART:20260101T110000Z\r\n"
            "DTEND:20260101T100000Z\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        no_summary = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:no-summary@example.com\r\n"
            "DTSTART:20260101T100000Z\r\n"
            "DTEND:20260101T110000Z\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        for label, ical in (("range", end_before_start), ("name", no_summary)):
            url = f"{self.calendar_url}/{label}-bad.ics"
            response = self.url_open(
                url, data=ical.encode(), headers=headers, method="PUT"
            )
            self.assertEqual(
                response.status_code, 400, f"{label}: got {response.status_code}"
            )

    def test_put_icalendar_update(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "text/calendar; charset=utf-8"

        ical_data = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Odoo//Test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{self.event1.ical_uid}\r\n"
            f"DTSTART:{self.event1.start.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"DTEND:{self.event1.stop.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            "SUMMARY:Updated Team Meeting\r\n"
            "DESCRIPTION:Updated description via CalDAV\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

        response = self.url_open(
            self.event1_url,
            data=ical_data.encode(),
            headers=headers,
            method="PUT",
        )

        self.assertEqual(response.status_code, 204)
        self.event1.invalidate_recordset(["name"])
        self.assertEqual(self.event1.name, "Updated Team Meeting")

    def test_delete_icalendar(self):
        temp_event = self.env["calendar.event"].create(
            {
                "name": "Delete This Event",
                "start": datetime.now() + timedelta(days=10),
                "stop": datetime.now() + timedelta(days=10, hours=1),
                "user_id": self.test_user.id,
            }
        )
        temp_event_url = f"{self.calendar_url}/{temp_event.id}.ics"

        response = self.url_open(
            temp_event_url,
            headers=self._get_auth_headers(),
            method="DELETE",
        )

        self.assertEqual(response.status_code, 204)
        temp_event.invalidate_recordset(["active"])
        self.assertTrue(temp_event.exists())
        self.assertFalse(temp_event.active)

    def test_report_calendar_query(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/xml; charset=utf-8"
        headers["Depth"] = "1"

        start_dt = datetime.now()
        end_dt = start_dt + timedelta(days=7)
        report_body = f"""<?xml version="1.0" encoding="utf-8"?>
        <CAL:calendar-query xmlns:D="DAV:" xmlns:CAL="urn:ietf:params:xml:ns:caldav">
            <D:prop>
                <D:getetag/>
                <CAL:calendar-data/>
            </D:prop>
            <CAL:filter>
                <CAL:comp-filter name="VCALENDAR">
                    <CAL:comp-filter name="VEVENT">
                        <CAL:time-range start="{start_dt.strftime("%Y%m%dT%H%M%SZ")}"
                                        end="{end_dt.strftime("%Y%m%dT%H%M%SZ")}"/>
                    </CAL:comp-filter>
                </CAL:comp-filter>
            </CAL:filter>
        </CAL:calendar-query>"""

        response = self.url_open(
            self.calendar_url,
            data=report_body.encode(),
            headers=headers,
            method="REPORT",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        responses = root.findall(".//{DAV:}response")
        self.assertEqual(len(responses), 2)
        self.assertTrue(root.findall(".//{urn:ietf:params:xml:ns:caldav}calendar-data"))

    def test_report_calendar_query_time_range_excludes(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/xml; charset=utf-8"

        start_dt = datetime.now() + timedelta(days=30)
        end_dt = start_dt + timedelta(days=7)
        report_body = f"""<?xml version="1.0" encoding="utf-8"?>
        <CAL:calendar-query xmlns:D="DAV:" xmlns:CAL="urn:ietf:params:xml:ns:caldav">
            <D:prop><D:getetag/></D:prop>
            <CAL:filter>
                <CAL:comp-filter name="VCALENDAR">
                    <CAL:comp-filter name="VEVENT">
                        <CAL:time-range start="{start_dt.strftime("%Y%m%dT%H%M%SZ")}"
                                        end="{end_dt.strftime("%Y%m%dT%H%M%SZ")}"/>
                    </CAL:comp-filter>
                </CAL:comp-filter>
            </CAL:filter>
        </CAL:calendar-query>"""

        response = self.url_open(
            self.calendar_url,
            data=report_body.encode(),
            headers=headers,
            method="REPORT",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        self.assertEqual(len(root.findall(".//{DAV:}response")), 0)

    def test_report_calendar_multiget(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/xml; charset=utf-8"

        report_body = f"""<?xml version="1.0" encoding="utf-8"?>
        <CAL:calendar-multiget xmlns:D="DAV:" xmlns:CAL="urn:ietf:params:xml:ns:caldav">
            <D:prop>
                <D:getetag/>
                <CAL:calendar-data/>
            </D:prop>
            <D:href>{self.event1_url}</D:href>
            <D:href>{self.calendar_url}/{self.event2.id}.ics</D:href>
        </CAL:calendar-multiget>"""

        response = self.url_open(
            self.calendar_url,
            data=report_body.encode(),
            headers=headers,
            method="REPORT",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        self.assertEqual(len(root.findall(".//{DAV:}response")), 2)

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
            self.calendar_url,
            data=sync_body.encode(),
            headers=headers,
            method="REPORT",
        )

        self.assertEqual(response.status_code, 207)
        root = etree.fromstring(response.content)
        sync_token_elem = root.find(".//{DAV:}sync-token")
        self.assertIsNotNone(sync_token_elem)
        self.assertTrue(sync_token_elem.text)
        self.assertGreater(
            len(root.findall(".//{DAV:}response")),
            0,
            "Initial sync should return events",
        )

        new_event = self.env["calendar.event"].create(
            {
                "name": "Incremental Sync Test",
                "start": datetime.now() + timedelta(days=15),
                "stop": datetime.now() + timedelta(days=15, hours=1),
                "user_id": self.test_user.id,
            }
        )
        self.event2.action_archive()
        self._bump_write_date(new_event | self.event2)

        sync_body_with_token = f"""<?xml version="1.0" encoding="utf-8"?>
        <D:sync-collection xmlns:D="DAV:">
            <D:sync-token>{sync_token_elem.text}</D:sync-token>
            <D:sync-level>1</D:sync-level>
            <D:prop>
                <D:getetag/>
            </D:prop>
        </D:sync-collection>"""

        response2 = self.url_open(
            self.calendar_url,
            data=sync_body_with_token.encode(),
            headers=headers,
            method="REPORT",
        )

        self.assertEqual(response2.status_code, 207)
        root2 = etree.fromstring(response2.content)
        responses2 = root2.findall(".//{DAV:}response")
        hrefs = {r.find(".//{DAV:}href").text: r for r in responses2}

        new_event_url = f"{self.calendar_url}/{new_event.id}.ics"
        self.assertIn(
            new_event_url, hrefs, "Incremental sync should return the new event"
        )

        archived_url = f"{self.calendar_url}/{self.event2.id}.ics"
        self.assertIn(archived_url, hrefs, "Incremental sync should report the removal")
        status = hrefs[archived_url].find(".//{DAV:}status")
        self.assertIsNotNone(status)
        self.assertIn("404", status.text)

        self.assertNotIn(self.event1_url, hrefs)

    def test_basic_auth(self):
        headers = self._get_auth_headers(use_bearer=False)
        headers["Depth"] = "0"

        response = self.url_open(
            self.calendar_home_url,
            headers=headers,
            method="PROPFIND",
        )
        self.assertNotEqual(response.status_code, 401)

    def test_unauthorized_access(self):
        response = self.url_open(self.calendar_home_url, method="PROPFIND")

        self.assertEqual(response.status_code, 401)
        self.assertIn("WWW-Authenticate", response.headers)

    def test_provision_default_calendars(self):
        other_user = self.env["res.users"].create(
            {"name": "Fresh Rep", "login": "fresh_rep_caldav"}
        )
        self.assertFalse(
            self.env["dav.calendar"].search([("user_id", "=", other_user.id)])
        )

        self.env["dav.calendar"]._provision_default_calendars(other_user)
        calendars = self.env["dav.calendar"].search([("user_id", "=", other_user.id)])
        self.assertEqual(calendars.mapped("name"), ["My Calendar"])

        self.env["dav.calendar"]._provision_default_calendars(other_user)
        self.assertEqual(
            self.env["dav.calendar"].search_count([("user_id", "=", other_user.id)]),
            1,
        )

    def test_get_records_sync_state(self):
        self.env["dav.sync.state"].search(
            [("device_id", "=", self.test_device.id)]
        ).unlink()

        response = self.url_open(self.event1_url, headers=self._get_auth_headers())
        self.assertEqual(response.status_code, 200)

        state = self.env["dav.sync.state"].search(
            [
                ("device_id", "=", self.test_device.id),
                ("resource_model", "=", "calendar.event"),
                ("resource_id", "=", self.event1.id),
            ]
        )
        self.assertEqual(len(state), 1)
        self.assertEqual(state.sync_status, "synced")
        self.assertEqual(state.resource_type, "event")

    def test_put_conflict_server_wins(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "text/calendar; charset=utf-8"
        headers["If-Match"] = '"deadbeefstale"'

        ical_data = (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Odoo//Test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{self.event1.ical_uid}\r\n"
            f"DTSTART:{self.event1.start.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"DTEND:{self.event1.stop.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            "SUMMARY:Should Not Apply\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        response = self.url_open(
            self.event1_url,
            data=ical_data.encode(),
            headers=headers,
            method="PUT",
        )
        self.assertEqual(response.status_code, 412)
        self.event1.invalidate_recordset(["name"])
        self.assertEqual(self.event1.name, "Team Meeting")

    def test_put_conflict_client_wins(self):
        device = self.env["device.device"].browse(self.test_device.id)
        state = self.env["dav.sync.state"].get_or_create_sync_state(
            device, "event", "calendar.event", self.event1.id
        )
        state.conflict_resolution_strategy = "client_wins"

        headers = self._get_auth_headers()
        headers["Content-Type"] = "text/calendar; charset=utf-8"
        headers["If-Match"] = '"deadbeefstale"'
        ical_data = (
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Odoo//Test//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{self.event1.ical_uid}\r\n"
            f"DTSTART:{self.event1.start.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"DTEND:{self.event1.stop.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            "SUMMARY:Client Wins Meeting\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        )
        response = self.url_open(
            self.event1_url,
            data=ical_data.encode(),
            headers=headers,
            method="PUT",
        )
        self.assertEqual(response.status_code, 204)
        self.event1.invalidate_recordset(["name"])
        self.assertEqual(self.event1.name, "Client Wins Meeting")

    def test_report_xxe_local_file_entity_rejected(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/xml; charset=utf-8"
        xxe_body = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<!DOCTYPE C:calendar-query [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b'<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">'
            b"<D:prop><D:getetag/><C:calendar-data>&xxe;</C:calendar-data></D:prop>"
            b"</C:calendar-query>"
        )
        response = self.url_open(
            self.calendar_url,
            data=xxe_body,
            headers=headers,
            method="REPORT",
        )
        self.assertNotIn(b"root:", response.content)

    def test_report_xxe_ssrf_entity_rejected(self):
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/xml; charset=utf-8"
        xxe_body = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<!DOCTYPE C:calendar-query [<!ENTITY xxe SYSTEM "http://169.254.169.254/latest/meta-data/">]>'
            b'<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">'
            b"<D:prop><D:getetag/><C:calendar-data>&xxe;</C:calendar-data></D:prop>"
            b"</C:calendar-query>"
        )
        response = self.url_open(
            self.calendar_url,
            data=xxe_body,
            headers=headers,
            method="REPORT",
        )
        self.assertNotIn(b"meta-data", response.content)

    def test_report_normal_request_still_parses(self):
        response = self.url_open(
            self.event1_url,
            headers=self._get_auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("BEGIN:VEVENT", response.content.decode())

    def test_caldav_disabled_returns_404(self):
        self.device_profile.dav_calendar_enabled = False
        response = self.url_open(
            self.calendar_home_url,
            headers=self._get_auth_headers(),
            method="PROPFIND",
        )
        self.assertEqual(response.status_code, 404)
