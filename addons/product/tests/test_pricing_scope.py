from odoo.exceptions import UserError, ValidationError
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

    def test_vendor_line_template_follows_its_variant(self):
        vendor = self.env["res.partner"].create({"name": "V"})
        seller = self.env["product.supplierinfo"].create(
            {"partner_id": vendor.id, "product_id": self.product_sofa_red.id}
        )
        self.assertEqual(seller.product_tmpl_id, self.product_template_sofa)
        seller.product_id = self.product
        self.assertEqual(seller.product_tmpl_id, self.product.product_tmpl_id)

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


@tagged("post_install", "-at_install")
class TestSellerPartnerMatching(ProductVariantsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create(
            {"name": "Vendor Co", "is_company": True}
        )
        cls.office = cls.env["res.partner"].create(
            {"name": "Office", "parent_id": cls.vendor.id}
        )
        cls.clerk = cls.env["res.partner"].create(
            {"name": "Clerk", "parent_id": cls.office.id}
        )
        cls.seller = cls.env["product.supplierinfo"].create(
            {
                "partner_id": cls.vendor.id,
                "product_tmpl_id": cls.product_template_sofa.id,
                "product_code": "VSOFA",
                "product_name": "Vendor sofa",
            }
        )

    def test_a_contact_of_the_vendor_sees_the_vendor_reference_everywhere(self):
        sofa = self.product_sofa_red.with_context(partner_id=self.clerk.id)
        self.assertEqual(sofa.code, "VSOFA")
        self.assertIn("VSOFA", sofa.partner_ref)
        self.assertIn("VSOFA", sofa.display_name)
        self.assertIn(
            self.product_sofa_red.id,
            [
                product_id
                for product_id, _name in self.env["product.product"]
                .with_context(partner_id=self.clerk.id)
                .name_search("VSOFA")
            ],
        )
        self.assertEqual(
            self.product_sofa_red._select_seller(partner_id=self.clerk), self.seller
        )

    def test_the_nearest_vendor_level_wins(self):
        parent_line = self.env["product.supplierinfo"].create(
            {
                "partner_id": self.office.id,
                "product_tmpl_id": self.product_template_sofa.id,
                "product_code": "OFFICE",
                "price": 20.0,
                "sequence": 2,
            }
        )
        self.seller.write({"price": 10.0, "sequence": 1})
        self.assertEqual(
            self.product_sofa_red._select_seller(partner_id=self.clerk), parent_line
        )
        self.assertEqual(
            self.product_sofa_red.with_context(partner_id=self.clerk.id).code, "OFFICE"
        )

    def test_the_nearest_vendor_level_wins_over_a_variant_line_further_up(self):
        self.seller.product_id = self.product_sofa_red
        self.env["product.supplierinfo"].create(
            {
                "partner_id": self.clerk.id,
                "product_tmpl_id": self.product_template_sofa.id,
                "product_code": "CLERK",
            }
        )
        sofa = self.product_sofa_red.with_context(partner_id=self.clerk.id)
        self.assertEqual(sofa.code, "CLERK")
        self.assertIn("[CLERK]", sofa.display_name)
        self.assertNotIn("VSOFA", sofa.display_name)

    def test_another_companys_variant_line_leaves_the_shared_line(self):
        other = self.env["res.company"].create({"name": "Other"})
        self.env["product.supplierinfo"].create(
            {
                "partner_id": self.vendor.id,
                "product_tmpl_id": self.product_template_sofa.id,
                "product_id": self.product_sofa_red.id,
                "product_code": "ELSEWHERE",
                "company_id": other.id,
            }
        )
        sofa = self.product_sofa_red.with_context(
            partner_id=self.vendor.id, company_id=self.env.company.id
        )
        self.assertIn("[VSOFA]", sofa.display_name)

    def test_a_parent_companys_vendor_name_shows_in_a_branch(self):
        branch = self.env["res.company"].create(
            {"name": "Branch", "parent_id": self.env.company.id}
        )
        self.seller.company_id = self.env.company
        sofa = self.product_sofa_red.with_context(
            partner_id=self.vendor.id, company_id=branch.id
        )
        self.assertIn("Vendor sofa", sofa.display_name)

    def test_a_partner_deleted_after_it_was_read_matches_no_seller(self):
        clerk = self.env["res.partner"].create(
            {"name": "Gone", "parent_id": self.office.id}
        )
        self.assertEqual(clerk.commercial_partner_id, self.vendor)
        clerk.unlink()
        sofa = self.product_sofa_red.with_context(partner_id=clerk.id)
        self.assertEqual(sofa.code, sofa.default_code)
        self.assertNotIn("VSOFA", sofa.display_name)

    def test_the_partners_own_line_wins_over_its_companys(self):
        own = self.env["product.supplierinfo"].create(
            {
                "partner_id": self.clerk.id,
                "product_tmpl_id": self.product_template_sofa.id,
                "product_code": "CLERK",
            }
        )
        self.assertEqual(
            self.product_sofa_red._get_contextual_partner_seller(
                self.clerk._get_seller_partners()
            ),
            own,
        )


@tagged("post_install", "-at_install")
class TestPackagingBarcodes(ProductVariantsCommon):
    def test_a_shared_packaging_barcode_collides_with_a_company_one(self):
        self.env["product.uom"].create(
            {
                "product_id": self.product_sofa_red.id,
                "uom_id": self.uom_unit.id,
                "barcode": "PK-1",
                "company_id": False,
            }
        )
        with self.assertRaisesRegex(ValidationError, "PK-1"):
            self.env["product.uom"].create(
                {
                    "product_id": self.product_sofa_blue.id,
                    "uom_id": self.uom_unit.id,
                    "barcode": "PK-1",
                    "company_id": self.env.company.id,
                }
            )

    def test_companies_may_reuse_a_packaging_barcode(self):
        other = self.env["res.company"].create({"name": "Other"})
        self.env["product.uom"].create(
            {
                "product_id": self.product_sofa_red.id,
                "uom_id": self.uom_unit.id,
                "barcode": "PK-2",
                "company_id": self.env.company.id,
            }
        )
        self.env.user.company_ids += other
        self.env["product.uom"].with_context(
            allowed_company_ids=(self.env.company | other).ids
        ).create(
            {
                "product_id": self.product_sofa_blue.id,
                "uom_id": self.uom_unit.id,
                "barcode": "PK-2",
                "company_id": other.id,
            }
        )


@tagged("post_install", "-at_install")
class TestCurrencyDeactivation(ProductVariantsCommon):
    def test_pricelists_of_all_the_users_companies_are_archived(self):
        other = self.env["res.company"].create({"name": "Second"})
        both = self.env.company | other
        admin = self.env["res.users"].create(
            {
                "name": "Two Company Admin",
                "login": "two_company_currency_admin",
                "company_id": self.env.company.id,
                "company_ids": [Command.set(both.ids)],
                "group_ids": [
                    Command.link(self.env.ref("base.group_system").id),
                    Command.link(self.env.ref("product.group_product_manager").id),
                ],
            }
        )
        currency = self.env.ref("base.SEK")
        currency.active = True
        here, there = self.env["product.pricelist"].create(
            [
                {
                    "name": "Here",
                    "currency_id": currency.id,
                    "company_id": self.env.company.id,
                },
                {"name": "There", "currency_id": currency.id, "company_id": other.id},
            ]
        )
        currency.with_user(admin).with_context(
            allowed_company_ids=self.env.company.ids
        ).active = False
        self.assertFalse(here.active)
        self.assertFalse(
            there.active,
            "the admin belongs to the second company even with only the first"
            " one active in the session",
        )
