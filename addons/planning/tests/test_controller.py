from datetime import datetime

from freezegun import freeze_time
from lxml import html

from odoo import tools
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase, tagged

from .common import TestCommonPlanning


@tagged("post_install", "-at_install")
class TestControllersRoute(HttpCase, TestCommonPlanning):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.classPatch(cls.env.cr, "now", datetime.now)
        with freeze_time("2023-06-01"):
            cls.setUpEmployees()

        calendar_bert = cls.env["resource.calendar"].create(
            {
                "name": "Calendar 2",
                "tz": "UTC",
                "hours_per_day": 4,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Thursday Morning",
                            "dayofweek": "3",
                            "hour_from": 13,
                            "hour_to": 17,
                            "day_period": "morning",
                        },
                    ),
                ],
            }
        )

        role_a = cls.env["resource.role"].create({"name": "role a"})

        cls.employee_bert.resource_calendar_id = calendar_bert
        cls.resource_bert.write({"default_role_id": role_a})
        cls.slots = cls.env["planning.slot"].create(
            [
                {
                    "resource_id": cls.resource_bert.id,
                    "resource_type": "human",
                    "start_datetime": datetime(2023, 6, 2, 8, 0),
                    "end_datetime": datetime(2023, 6, 2, 17, 0),
                },
                {
                    "resource_id": cls.resource_bert.id,
                    "resource_type": "human",
                    "start_datetime": datetime(2023, 6, 3, 8, 0),
                    "end_datetime": datetime(2023, 6, 3, 17, 0),
                },
                {
                    "resource_id": cls.resource_bert.id,
                    "resource_type": "human",
                    "start_datetime": datetime(2023, 6, 4, 8, 0),
                    "end_datetime": datetime(2023, 6, 4, 17, 0),
                },
            ]
        )

    def test_slot_ics_file_and_google_cal_url(self):

        ics_url = self.slots[0]._get_ics_url(self.slots[0].resource_id.partner_id)
        self.authenticate(None, None)
        ics_request = self.url_open(ics_url)
        self.assertEqual(ics_request.status_code, 200, "Response should = OK")
        decoded_content = ics_request.content.decode("utf-8")
        self.assertIn(
            "DTSTART:20230602T080000Z",
            decoded_content,
            "The starting date of the shift should be in the ics file",
        )
        self.assertIn(
            "DTEND:20230602T170000Z",
            decoded_content,
            "The ending date of the shift should be in the ics file",
        )
        self.assertIn(
            "SUMMARY:role",
            decoded_content,
            "The summary of the ics file should contain the name of the employee and it's default role",
        )
        self.assertIn(
            "Role: role a",
            decoded_content,
            "The description of the ics file should contain the role of the employee",
        )

        google_calendar_url = self.slots[0]._get_slot_resource_urls()["google_url"]
        self.assertIn(
            "dates=20230602T100000%2F20230602T190000",
            google_calendar_url,
            "The starting date of the shift should be in the google calendar url",
        )
        self.assertIn(
            "text=role+a",
            google_calendar_url,
            "The name of the employee and it's default role should be in the google calendar url title",
        )

    def test_planning_page_formats_its_period_in_the_employee_timezone(self):
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.resource_bert.id,
                "resource_type": "human",
                "start_datetime": datetime(2023, 6, 1, 17, 0),
                "end_datetime": datetime(2023, 6, 1, 21, 0),
            }
        )
        slot.action_planning_publish_and_send()
        planning = self.env["planning.planning"].search(
            [
                ("start_datetime", "=", slot.start_datetime),
                ("end_datetime", "=", slot.end_datetime),
            ]
        )
        self.employee_bert.tz = "America/New_York"
        self.env.flush_all()
        url = self.employee_bert.resource_id._planning_get_url(
            planning.start_datetime, planning.end_datetime, planning
        )[self.employee_bert.resource_id.id]

        response = self.url_open(url)

        self.assertEqual(response.status_code, 200)
        [banner_div] = html.fromstring(response.text).xpath(
            "//div[hasclass('o_shift_info')][contains(., 'Shifts from')]"
        )
        banner = " ".join(banner_div.text_content().split())

        def in_new_york(dt, dt_format):
            return tools.format_datetime(
                self.env, dt, tz="America/New_York", dt_format=dt_format
            )

        expected = (
            f"Shifts from {in_new_york(planning.start_datetime, 'E')}. "
            f"{in_new_york(planning.start_datetime, 'short')} "
            f"to {in_new_york(planning.end_datetime, 'E')}. "
            f"{in_new_york(planning.end_datetime, 'short')}"
        )
        self.assertEqual(banner, " ".join(expected.split()))

    def test_planning_ics_file(self):

        self.slots.action_planning_publish_and_send()
        start, end = (
            min(self.slots.mapped("start_datetime")),
            max(self.slots.mapped("end_datetime")),
        )
        planning_published = self.env["planning.planning"].search(
            [("start_datetime", "=", start), ("end_datetime", "=", end)]
        )
        feed = "/planning/%s/%s.ics" % (
            planning_published.access_token,
            self.employee_bert.resource_id.sudo().planning_token,
        )
        req = self.url_open(feed)

        self.assertEqual(req.status_code, 200, "Response should = OK")
        decoded_content = req.content.decode("utf-8")
        self.assertEqual(
            decoded_content.count("BEGIN:VEVENT"),
            3,
            "There should be 3 Calendar events present in the ics file",
        )

    def test_planning_fields_import_compatible_export(self):
        self.authenticate("admin", "admin")
        response = self.url_open(
            "/web/export/get_fields",
            data=json_dumps(
                {
                    "params": {
                        "model": "planning.slot.template",
                        "import_compat": True,
                        "domain": [],
                    }
                }
            ),
            headers={"Content-Type": "application/json"},
        )

        response_data = json_loads(response.content)["result"]
        actual_exported_fields = {
            field["value"] for field in response_data if field["default_export"]
        }

        expected_exported_fields = {"duration_days", "start_time", "end_time"}

        self.assertEqual(
            actual_exported_fields,
            expected_exported_fields,
            "The default exported fields should be matched",
        )

    def test_planning_ics_file_without_assigned_employee(self):
        if self.env.company.resource_calendar_id.tz != "Europe/Brussels":
            self.env.company.resource_calendar_id.tz = "Europe/Brussels"
        self.slots[0].write({"resource_id": False})
        ics_url = self.slots[0]._get_ics_url(self.env["res.partner"])
        self.authenticate(None, None)

        ics_request = self.url_open(ics_url)
        self.assertEqual(
            ics_request.status_code, 200, "ICS export should return HTTP 200 OK"
        )
        decoded_content = ics_request.content.decode("utf-8")

        self.assertIn(
            "DTSTART:20230602T080000Z",
            decoded_content,
            "The starting date of the shift should be in the ics file",
        )
        self.assertIn(
            "DTEND:20230602T170000Z",
            decoded_content,
            "The ending date of the shift should be in the ics file",
        )
        self.assertIn(
            "SUMMARY:role",
            decoded_content,
            "The summary of the ics file should contain the name of the employee and it's default role",
        )
        self.assertIn(
            "Role: role a",
            decoded_content,
            "The description of the ics file should contain the role of the employee",
        )
