from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestResourceLifecycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Resource = cls.env["resource.resource"]
        cls.grid = cls.Resource.create(
            {"name": "Grid Supply", "type": "intangible", "tz": "UTC"}
        )

    def test_a_new_resource_is_available(self):
        self.assertEqual(self.grid.state, "available")

    def test_maintenance_ends_where_it_began(self):
        self.grid.action_set_in_service()
        self.grid.action_set_maintenance()
        self.assertEqual(self.grid.state_before_maintenance, "in_service")
        self.grid.action_end_maintenance()
        self.assertRecordValues(
            self.grid, [{"state": "in_service", "state_before_maintenance": False}]
        )

    def test_disposal_dates_and_archives_and_restoring_reverses_it(self):
        self.grid.action_dispose()
        self.assertFalse(self.grid.active)
        self.assertTrue(self.grid.date_disposal)
        self.grid.action_unarchive()
        self.assertRecordValues(
            self.grid,
            [{"active": True, "state": "out_of_service", "date_disposal": False}],
        )

    def test_only_an_archived_resource_is_reactivated(self):
        with patch.object(type(self.Resource), "_check_reactivation") as check:
            self.grid.write({"active": True})
        check.assert_not_called()

    def test_a_disposed_resource_needs_its_date(self):
        with self.assertRaises(ValidationError):
            self.grid.write({"state": "disposed"})
