from odoo.exceptions import UserError
from odoo.fields import Date
from odoo.tests.common import TransactionCase


class TestWorkEntryModificationGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Guarded employee",
                "date_version": Date.to_date("2025-01-01"),
                "contract_date_start": Date.to_date("2025-01-01"),
            }
        )
        cls.work_entry_type = cls.env["hr.work.entry.type"].create(
            {"name": "Guard test", "code": "GUARDTEST100"}
        )
        cls.validated_entry, cls.draft_entry = cls.env["hr.work.entry"].create(
            [
                {
                    "name": "Validated entry",
                    "employee_id": cls.employee.id,
                    "version_id": cls.employee.version_id.id,
                    "work_entry_type_id": cls.work_entry_type.id,
                    "date": Date.to_date("2025-03-03"),
                    "duration": 8.0,
                },
                {
                    "name": "Draft entry",
                    "employee_id": cls.employee.id,
                    "version_id": cls.employee.version_id.id,
                    "work_entry_type_id": cls.work_entry_type.id,
                    "date": Date.to_date("2025-03-04"),
                    "duration": 8.0,
                },
            ]
        )
        cls.validated_entry.state = "validated"

    def test_check_modification_allowed_refuses_a_validated_entry(self):
        """The gantt asks the server before touching a selection, so the server must answer."""
        with self.assertRaises(UserError):
            (self.validated_entry | self.draft_entry).check_modification_allowed()

    def test_check_modification_allowed_lets_a_draft_through(self):
        self.draft_entry.check_modification_allowed()

    def test_setting_a_validated_entry_back_to_draft_still_works(self):
        """Extracting the guard must not swallow the `state` escape `write` relies on."""
        self.validated_entry.action_set_to_draft()
        self.assertEqual(self.validated_entry.state, "draft")
