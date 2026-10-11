import odoo
from odoo.tests import Form

from odoo.addons.point_of_sale.tests.test_res_config_settings import TestConfigureShops


@odoo.tests.tagged("post_install", "-at_install")
class TestConfigureShopsEnterprise(TestConfigureShops):

    def _remove_on_payment_taxes(self):
        self.env["account.tax"].search(
            [
                ("company_ids", "in", [self.env.company.id]),
                ("tax_exigibility", "=", "on_payment"),
            ]
        ).unlink()

    def test_should_not_affect_other_pos_config(self):
        self._remove_on_payment_taxes()

        pos_config1 = self.env["pos.config"].create(
            {"name": "Shop 1", "module_pos_restaurant": False}
        )
        pos_config2 = self.env["pos.config"].create(
            {"name": "Shop 2", "module_pos_restaurant": False}
        )
        self.assertEqual(pos_config1.receipt_header, False)
        self.assertEqual(pos_config2.receipt_header, False)

        with Form(self.env["res.config.settings"]) as form:
            form.pos_config_id = pos_config1
            form.pos_is_header_or_footer = True
            form.pos_receipt_header = "xxxxx"
            form.account_tax_return_journal_id = self.account_tax_return_journal

        self.assertEqual(pos_config1.receipt_header, "xxxxx")
        self.assertEqual(pos_config2.receipt_header, False)

        with Form(self.env["res.config.settings"]) as form:
            form.pos_config_id = pos_config2
            form.pos_is_header_or_footer = True
            form.pos_receipt_header = "yyyyy"
            form.account_tax_return_journal_id = self.account_tax_return_journal

        self.assertEqual(pos_config1.receipt_header, "xxxxx")
        self.assertEqual(pos_config2.receipt_header, "yyyyy")

    def test_is_header_or_footer_to_false(self):
        self._remove_on_payment_taxes()

        pos_config = self.env["pos.config"].create(
            {
                "name": "Shop",
                "is_header_or_footer": True,
                "module_pos_restaurant": False,
                "receipt_header": "header val",
                "receipt_footer": "footer val",
            }
        )

        with Form(self.env["res.config.settings"]) as form:
            form.pos_config_id = pos_config
            form.pos_is_header_or_footer = False
            form.account_tax_return_journal_id = self.account_tax_return_journal

        self.assertEqual(pos_config.receipt_header, False)
        self.assertEqual(pos_config.receipt_footer, False)
