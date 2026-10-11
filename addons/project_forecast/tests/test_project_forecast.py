from datetime import datetime, timedelta

from odoo.exceptions import UserError
from odoo.tests import freeze_time
from odoo.tests.common import TransactionCase, tagged

FROZEN_NOW = datetime(2026, 6, 15, 8, 0)


@freeze_time(FROZEN_NOW)
@tagged("post_install", "-at_install")
class TestProjectForecast(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Forecast Project"})

    def _slot(self, hours, start_offset_days=1, **extra):
        start = FROZEN_NOW + timedelta(days=start_offset_days)
        return self.env["planning.slot"].create(
            {
                "project_id": self.project.id,
                "start_datetime": start,
                "end_datetime": start + timedelta(hours=hours),
                **extra,
            }
        )

    def test_total_forecast_time_sums_slots(self):
        self._slot(3)
        self._slot(5, start_offset_days=2)
        self.assertEqual(self.project.total_forecast_time, 8)

        empty = self.env["project.project"].create({"name": "No Shifts"})
        self.assertEqual(empty.total_forecast_time, 0)

    def test_company_change_blocked_by_foreign_slots(self):
        self._slot(2)
        other_company = self.env["res.company"].create({"name": "Sucursal B"})
        with self.assertRaises(UserError):
            self.project.company_id = other_company

    def test_slot_template_display_name_carries_project(self):
        template = self.env["planning.slot.template"].create(
            {
                "start_time": 8.0,
                "duration_days": 1,
                "project_id": self.project.id,
            }
        )
        self.assertIn("[Forecast Project]", template.display_name)

    def test_forecast_action_context_targets_project(self):
        later = self._slot(4, start_offset_days=5)
        earliest = self._slot(4, start_offset_days=3)
        action = self.project.action_project_forecast_from_project()
        self.assertEqual(action["context"]["default_project_id"], self.project.id)
        self.assertEqual(action["context"]["initialDate"], earliest.start_datetime)
        self.assertNotEqual(later.start_datetime, earliest.start_datetime)
        self.assertFalse(action["context"]["search_default_group_by_resource"])
