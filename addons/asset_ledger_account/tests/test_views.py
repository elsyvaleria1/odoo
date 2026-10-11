import lxml.etree as ET

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestViewExtensions(TransactionCase):
    def test_the_asset_pivot_row_is_available_not_default(self):
        pivot = self.env.ref("analytic.view_account_analytic_line_pivot")
        arch = self.env["account.analytic.line"].get_view(pivot.id, "pivot")["arch"]

        asset = ET.fromstring(arch).find(".//field[@name='asset_id']")

        self.assertIsNotNone(asset, "the field is still offered to the pivot")
        self.assertEqual(
            asset.get("invisible"),
            "1",
            "pivot_arch_parser drops an invisible field before reading its "
            "type, so this is what keeps Asset out of everyone's default "
            "row grouping",
        )

    def test_the_bills_button_hides_itself_when_there_are_none(self):
        form = self.env.ref("asset_ledger.resource_asset_view_form_ledger")
        arch = self.env["resource.resource"].get_view(form.id, "form")["arch"]

        button = ET.fromstring(arch).find(".//button[@name='action_view_bills']")

        self.assertIsNotNone(button)
        self.assertEqual(button.get("invisible"), "count_bill == 0")
