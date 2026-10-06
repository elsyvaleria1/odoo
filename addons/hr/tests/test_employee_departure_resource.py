from datetime import date

from freezegun import freeze_time

from odoo.tests import tagged

from .common import TestHrCommon


@tagged("post_install", "-at_install")
class TestDepartureDisposesTheResource(TestHrCommon):
    """A departure is the person's disposal: on its date their resource is
    disposed, which archives it and ends what they held."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.leaving = cls.env["hr.employee"].create(
            {"name": "Leaving", "contract_date_start": "2026-01-01"}
        )

    def _register(self, departure_date):
        self.env["wizard.hr.employee.register.departure"].with_user(
            self.res_users_hr_officer
        ).with_context(active_ids=self.leaving.ids).create(
            {
                "departure_reason_id": self.env.ref("hr.departure_resigned").id,
                "departure_date": departure_date,
            }
        ).action_register_departure()

    @freeze_time("2026-03-10")
    def test_a_departure_today_disposes_the_resource(self):
        self._register(date(2026, 3, 10))
        self.assertRecordValues(
            self.leaving.resource_id,
            [
                {
                    "state": "disposed",
                    "date_disposal": date(2026, 3, 10),
                    "active": False,
                }
            ],
        )
        self.assertEqual(self.leaving.resource_state, "disposed")
        self.assertFalse(self.leaving.active)

    def test_a_future_departure_waits_for_its_day(self):
        with freeze_time("2026-03-10"):
            self._register(date(2026, 3, 31))
            self.assertEqual(self.leaving.resource_id.state, "available")
            self.assertTrue(self.leaving.active)
        with freeze_time("2026-03-31"):
            self.env["hr.employee"]._cron_dispose_departed_resources()
            self.assertEqual(self.leaving.resource_id.state, "disposed")

    @freeze_time("2026-03-10")
    def test_a_rehire_brings_the_person_back_suspended(self):
        self._register(date(2026, 3, 10))
        self.leaving.action_unarchive()
        self.assertRecordValues(
            self.leaving.resource_id,
            [{"state": "out_of_service", "date_disposal": False, "active": True}],
        )
