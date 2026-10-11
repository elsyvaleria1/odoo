from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "accruals")
class TestAccrualLevelExport(HttpCase):

    def _import_compatible_field_names(self, model):
        self.authenticate("admin", "admin")
        result = self.call_jsonrpc(
            "/web/export/get_fields",
            {"model": model, "domain": [], "import_compat": True},
        )
        return {field["id"] for field in result}

    def test_user_editable_accrual_level_fields_are_exportable(self):
        field_names = self._import_compatible_field_names("hr.leave.accrual.level")

        self.assertIn("action_with_unused_accruals", field_names)
        self.assertIn("carryover_options", field_names)
        self.assertIn("accrual_validity", field_names)
