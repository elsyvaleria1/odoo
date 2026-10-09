from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import Form, tagged

from odoo.addons.product.tests.common import ProductVariantsCommon


@tagged("post_install", "-at_install")
class TestPricingScope(ProductVariantsCommon):
    def test_rule_company_follows_its_template(self):
        rule = self.env["product.pricelist.item"].create(
            {
                "product_tmpl_id": self.product_template_sofa.id,
                "fixed_price": 3.0,
                "pricelist_id": False,
            }
        )
        self.assertFalse(rule.company_id)
        self.product_template_sofa.company_id = self.env.company
        self.assertEqual(rule.company_id, self.env.company)

    def test_company_currency_change_realigns_only_its_default_pricelist(self):
        usd, eur, gbp = (
            self.env.ref("base.USD"),
            self.env.ref("base.EUR"),
            self.env.ref("base.GBP"),
        )
        company = self.env["res.company"].create(
            {"name": "Currency Co", "currency_id": usd.id}
        )
        default, sterling = self.env["product.pricelist"].create(
            [
                {"name": "Default", "company_id": company.id, "currency_id": usd.id},
                {"name": "Sterling", "company_id": company.id, "currency_id": gbp.id},
            ]
        )
        company.currency_id = eur
        self.assertEqual(default.currency_id, eur)
        self.assertEqual(
            sterling.currency_id,
            gbp,
            "a pricelist deliberately kept in another currency is not the"
            " company's default and keeps its currency",
        )

    def test_branch_uses_its_parent_companys_vendor_prices(self):
        branch = self.env["res.company"].create(
            {"name": "Branch", "parent_id": self.env.company.id}
        )
        seller = self.env["product.supplierinfo"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "V"}).id,
                "product_tmpl_id": self.product_template_sofa.id,
                "company_id": self.env.company.id,
            }
        )
        self.assertEqual(
            seller._filtered_for_company_and_product(branch, self.product_sofa_red),
            seller,
        )
        other = self.env["res.company"].create({"name": "Unrelated"})
        self.assertFalse(
            seller._filtered_for_company_and_product(other, self.product_sofa_red)
        )

    def test_vendor_unit_follows_an_incompatible_product_change(self):
        kg_product = self.env["product.template"].create(
            {"name": "Flour", "uom_id": self.env.ref("uom.product_uom_kgm").id}
        )
        seller = self.env["product.supplierinfo"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "V"}).id,
                "product_tmpl_id": self.product_template_sofa.id,
            }
        )
        self.assertEqual(seller.product_uom_id, self.uom_unit)
        seller.product_tmpl_id = kg_product
        self.assertEqual(seller.product_uom_id, kg_product.uom_id)

    def test_tag_copy_keeps_an_explicit_name(self):
        tag = self.env["product.tag"].create({"name": "Sale"})
        self.assertEqual(tag.copy({"name": "Promo"}).name, "Promo")
        self.assertIn("(copy)", tag.copy().name)

    def test_a_vanished_label_layout_is_reported(self):
        layout = self.env["wizard.product.product.print.label"].create({})
        layout_id = layout.id
        layout.unlink()
        with self.assertRaisesRegex(UserError, "no longer available"):
            self.env[
                "report.product.report_producttemplatelabel_dymo"
            ]._get_report_values(
                docids=[],
                data={
                    "layout_wizard": layout_id,
                    "active_model": "product.template",
                    "quantity_by_product": {str(self.product_template_sofa.id): 1},
                },
            )


@tagged("post_install", "-at_install")
class TestAttributeValuePropagateScope(ProductVariantsCommon):
    def test_a_new_default_is_not_mistaken_for_customizations(self):
        self.color_attribute_red.default_extra_price = 15.0
        wizard = Form.from_action(
            self.env, self.color_attribute_red.action_update_prices()
        ).save()
        self.assertEqual(wizard.product_count, 1)
        self.assertEqual(wizard.changed_product_count, 1)
        self.assertNotIn("customized", wizard.message)

    def test_a_value_archived_meanwhile_comes_back_at_the_new_price(self):
        template = self.product_template_sofa
        red_variant = self.product_sofa_red
        self.env["product.combo"].create(
            {
                "name": "Keeps red",
                "combo_item_ids": [Command.create({"product_id": red_variant.id})],
            }
        )
        line = template.attribute_line_ids
        line.value_ids = [Command.unlink(self.color_attribute_red.id)]
        self.assertFalse(red_variant.active, "referenced, so archived and kept")

        self.color_attribute_red.default_extra_price = 9.0
        Form.from_action(
            self.env, self.color_attribute_red.action_update_prices()
        ).save().action_confirm()

        line.value_ids = [Command.link(self.color_attribute_red.id)]
        self.assertEqual(
            line.product_template_value_ids.filtered(
                lambda ptav: ptav.product_attribute_value_id == self.color_attribute_red
            ).price_extra,
            9.0,
        )

    def test_archived_products_are_not_counted(self):
        archived = self.env["product.template"].create(
            {
                "name": "Old sofa",
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": self.color_attribute.id,
                            "value_ids": [Command.set(self.color_attribute_red.ids)],
                        }
                    )
                ],
            }
        )
        archived.action_archive()
        self.color_attribute_red.default_extra_price = 15.0
        wizard = Form.from_action(
            self.env, self.color_attribute_red.action_update_prices()
        ).save()
        self.assertEqual(wizard.product_count, 1)

    def test_add_counts_only_products_missing_the_value(self):
        self.env["product.template"].create(
            {
                "name": "Chair",
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": self.color_attribute.id,
                            "value_ids": [Command.set(self.color_attribute_blue.ids)],
                        }
                    )
                ],
            }
        )
        wizard = Form.from_action(
            self.env, self.color_attribute_red.action_add_to_products()
        ).save()
        self.assertEqual(
            wizard.product_count,
            1,
            "the sofa already carries red; only the chair would gain it",
        )
