from unittest.mock import patch

from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.base.tests.common import HttpCaseWithUserPortal


@tagged("post_install", "-at_install")
class TestSaleExternalTaxesSalePortal(HttpCaseWithUserPortal):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fp_external = cls.env["account.fiscal.position"].create(
            {
                "name": "External",
            }
        )
        cls.product_test = cls.env["product.product"].create(
            {
                "name": "Test product",
                "list_price": 10.00,
                "standard_price": 10.00,
                "supplier_taxes_id": None,
            }
        )

    def _create_sale_order(self, partner):
        return self.env["sale.order"].create(
            {
                "name": "test",
                "partner_id": partner.id,
                "fiscal_position_id": self.fp_external.id,
                "date_order": "2023-01-01",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_test.id,
                            "tax_ids": None,
                            "price_unit": self.product_test.list_price,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Optional Products",
                            "display_type": "line_section",
                            "is_optional": True,
                        }
                    ),
                    Command.create(
                        {
                            "name": "optional product",
                            "price_unit": 1,
                            "product_qty": 0,
                            "product_id": self.env["product.product"]
                            .create({"name": "optional product"})
                            .id,
                        }
                    ),
                ],
            }
        )

    def test_01_portal_test_optional_products(self):
        self.env["product.pricelist"].search([]).unlink()
        portal_partner = (
            self.env["res.users"].sudo().search([("login", "=", "portal")]).partner_id
        )
        portal_partner.write(
            {
                "state_id": self.env.ref("base.state_us_25").id,
                "zip": "07002",
                "country_id": self.env.ref("base.us").id,
            }
        )
        order = self._create_sale_order(portal_partner)

        self.env.ref("sale.sale_order_comp_rule").active = False
        self.env.ref("sale.sale_order_line_comp_rule").active = False

        order.action_quotation_sent()

        mixin_path = "odoo.addons.account_external_tax.models.mixin_account_external_tax.MixinAccountExternalTax"
        with (
            patch(
                f"{mixin_path}._get_and_set_external_taxes_on_eligible_records"
            ) as mocked_get_and_set,
            patch(
                f"{mixin_path}._compute_is_tax_computed_externally",
                lambda self: self.write({"is_tax_computed_externally": True}),
            ),
        ):
            self.start_tour("/", "sale_external_optional_products", login="portal")
            mocked_get_and_set.assert_called()

            self.assertEqual(
                mocked_get_and_set.call_count,
                3,
                "External taxes were not calculated enough times during this tour.",
            )
