from datetime import datetime, time, timedelta

from odoo import fields
from odoo.tests import tagged

from .common import TestCommonPlanning
from odoo.addons.mail.tests.common import MailCommon


@tagged("post_install", "-at_install")
class TestContractorResource(TestCommonPlanning, MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contractor = cls.env["res.partner"].create(
            {"name": "Outside Welder", "email": "welder@example.com"}
        )
        (cls.resource,) = cls.contractor._get_or_create_resources(cls.env.company)
        today = fields.Date.today()
        next_monday = today + timedelta(days=-today.weekday() % 7)
        cls.start = datetime.combine(next_monday, time(9))

    def _plan(self, **vals):
        return self.env["planning.slot"].create(
            {
                "resource_id": self.resource.id,
                "start_datetime": self.start,
                "end_datetime": self.start + timedelta(hours=4),
                **vals,
            }
        )

    def test_a_contractor_is_planned_without_being_an_employee(self):
        slot = self._plan()
        self.assertEqual(slot.resource_type, "human")
        self.assertFalse(slot.employee_id)
        self.assertGreater(slot.allocated_hours, 0)
        self.assertFalse(self.contractor.employee_ids)

    def test_the_gantt_reads_a_contractor_row(self):
        slot = self._plan()
        window = (self.start - timedelta(days=1), self.start + timedelta(days=6))
        bar = self.env["planning.slot"]._gantt_progress_bar(
            "resource_id", self.resource.ids, *window
        )
        self.assertEqual(bar[self.resource.id]["value"], slot.allocated_hours)
        self.assertFalse(bar[self.resource.id]["employee_id"])
        periods = self.env["planning.slot"]._gantt_resource_employees_working_periods(
            [{"resource_id": (self.resource.id, self.resource.name)}],
            str(window[0]),
            str(window[1]),
        )
        self.assertNotIn(self.resource.id, periods)

    def test_a_contractor_is_mailed_their_schedule(self):
        slot = self._plan()
        wizard = (
            self.env["wizard.planning.slot.publish"]
            .with_context(active_model="planning.slot")
            .create(
                {
                    "start_datetime": self.start - timedelta(days=1),
                    "end_datetime": self.start + timedelta(days=6),
                }
            )
        )
        self.assertIn(self.resource, wizard.resource_ids)
        self.assertNotIn(self.resource, wizard.resources_no_email)
        with self.mock_mail_gateway():
            wizard.action_send()
        self.assertMailMailWEmails(
            [self.contractor.email],
            "outgoing",
            fields_values={"email_to": self.contractor.email},
        )
        body = self._new_mails.filtered(
            lambda mail: self.contractor.email in (mail.email_to or "")
        ).body_html
        self.assertIn(self.resource.planning_token, body)
        self.assertEqual(slot.state, "2_published")

    def test_a_person_without_an_email_is_named_not_mailed(self):
        nameless = self.env["res.partner"].create({"name": "No Address"})
        (resource,) = nameless._get_or_create_resources(self.env.company)
        self._plan(resource_id=resource.id)
        wizard = (
            self.env["wizard.planning.slot.publish"]
            .with_context(active_model="planning.slot")
            .create(
                {
                    "start_datetime": self.start - timedelta(days=1),
                    "end_datetime": self.start + timedelta(days=6),
                }
            )
        )
        self.assertIn(resource, wizard.resources_no_email)
        without_email = wizard.get_people_without_email()
        self.assertEqual(without_email["relation"], "resource.resource")
        self.assertIn(resource.id, without_email["res_ids"])

    def test_the_portal_link_names_the_contractor(self):
        self._plan()
        planning = self.env["planning.planning"].create(
            {
                "start_datetime": self.start - timedelta(days=1),
                "end_datetime": self.start + timedelta(days=6),
            }
        )
        url = self.resource._planning_get_url(
            planning.date_start, planning.date_end, planning
        )[self.resource.id]
        self.assertEqual(
            url,
            f"/planning/{planning._page_token(self.resource)}/{self.resource.planning_token}",
        )
        self.assertEqual(
            self.env["resource.resource"]
            .sudo()
            .search([("planning_token", "=", self.resource.planning_token)]),
            self.resource,
        )

    def test_sending_a_schedule_with_a_contractor_on_it(self):
        slot = self._plan()
        wizard = (
            self.env["wizard.planning.slot.publish"]
            .with_context(active_model="planning.slot")
            .create(
                {
                    "start_datetime": self.start - timedelta(days=1),
                    "end_datetime": self.start + timedelta(days=6),
                }
            )
        )
        self.assertIn(slot, wizard.slot_ids)
        self.assertIn(self.resource, wizard.resource_ids)
        self.assertEqual(wizard.action_send()["type"], "ir.actions.client")

    def test_a_contractor_takes_time_off_on_their_calendar(self):
        leave = self.env["resource.schedule.exception"].create(
            {
                "name": "Away",
                "resource_id": self.resource.id,
                "date_from": self.start,
                "date_to": self.start + timedelta(days=1),
            }
        )
        self.assertEqual(leave.calendar_id, self.resource.calendar_id)
