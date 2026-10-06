from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form
from odoo.tests.common import tagged

from odoo.addons.purchase_agreement.tests.common import TestPurchaseAgreementCommon


@tagged("post_install", "-at_install")
class TestPurchaseAgreement(TestPurchaseAgreementCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.currency.rate"].search([]).unlink()

    def test_00_purchase_agreement_users(self):
        self.assertTrue(
            self.user_purchase_agreement_manager, "Manager Should be created"
        )
        self.assertTrue(self.user_purchase_agreement_user, "User Should be created")

    def test_01_cancel_purchase_agreement(self):
        self.bo_agreement.with_user(self.user_purchase_agreement_user).action_cancel()
        self.assertEqual(
            self.bo_agreement.state,
            "cancel",
            "Agreement should be in cancelled state.",
        )
        self.bo_agreement.with_user(self.user_purchase_agreement_user).action_draft()
        self.bo_agreement.with_user(self.user_purchase_agreement_user).copy()

    def test_02_purchase_agreement(self):
        price_product09 = 34
        price_product13 = 62
        quantity = 26

        line1 = (
            0,
            0,
            {
                "product_id": self.product_09.id,
                "product_qty": quantity,
                "product_uom_id": self.product_uom_id.id,
                "price_unit": price_product09,
            },
        )
        line2 = (
            0,
            0,
            {
                "product_id": self.product_13.id,
                "product_qty": quantity,
                "product_uom_id": self.product_uom_id.id,
                "price_unit": price_product13,
            },
        )

        agreement_blanket = self.env["purchase.agreement"].create(
            {
                "line_ids": [line1, line2],
                "agreement_type": "blanket_order",
                "partner_id": self.res_partner_1.id,
            }
        )

        agreement_blanket.action_confirm()

        seller_partner1 = self.res_partner_1
        supplierinfo09 = self.env["product.supplierinfo"].search(
            [
                ("partner_id", "=", seller_partner1.id),
                ("product_id", "=", self.product_09.id),
                ("agreement_id", "=", agreement_blanket.id),
            ]
        )
        self.assertEqual(
            supplierinfo09.partner_id,
            seller_partner1,
            "The supplierinfo is not correct",
        )
        self.assertEqual(
            supplierinfo09.price, price_product09, "The supplierinfo is not correct"
        )

        supplierinfo13 = self.env["product.supplierinfo"].search(
            [
                ("partner_id", "=", seller_partner1.id),
                ("product_id", "=", self.product_13.id),
                ("agreement_id", "=", agreement_blanket.id),
            ]
        )
        self.assertEqual(
            supplierinfo13.partner_id,
            seller_partner1,
            "The supplierinfo is not correct",
        )
        self.assertEqual(
            supplierinfo13.price, price_product13, "The supplierinfo is not correct"
        )

        agreement_blanket.action_confirm()
        agreement_blanket.action_done()

        self.assertFalse(
            self.env["product.supplierinfo"].search([("id", "=", supplierinfo09.id)]),
            "The supplier info should be removed",
        )
        self.assertFalse(
            self.env["product.supplierinfo"].search([("id", "=", supplierinfo13.id)]),
            "The supplier info should be removed",
        )

    def test_03_blanket_order_rfq(self):

        bo_form = Form(self.env["purchase.agreement"])
        bo_form.partner_id = self.res_partner_1
        bo_form.agreement_type = "blanket_order"
        with bo_form.line_ids.new() as line:
            line.product_id = self.product_09
            line.product_qty = 5.0
            line.price_unit = 21
        bo = bo_form.save()
        bo.action_confirm()

        po_form = Form(
            self.env["purchase.order"].with_context(
                {"default_agreement_id": bo.id, "default_user_id": False}
            )
        )
        po = po_form.save()

        self.assertEqual(
            po.line_ids.price_unit,
            bo.line_ids.price_unit,
            "The blanket order unit price should have been copied to purchase order",
        )
        self.assertEqual(
            po.partner_id,
            bo.partner_id,
            "The blanket order vendor should have been copied to purchase order",
        )

        po_form = Form(po)
        po_form.line_ids.remove(0)
        with po_form.line_ids.new() as line:
            line.product_id = self.product_09
            line.product_qty = 5.0

        po = po_form.save()
        po.action_confirm()
        self.assertEqual(
            po.line_ids.price_unit,
            bo.line_ids.price_unit,
            "The blanket order unit price should still be copied to purchase order",
        )
        self.assertEqual(po.state, "done")

    def test_06_purchase_agreement(self):
        product = self.env["product.product"].create(
            {
                "name": "test6",
            }
        )
        product2 = self.env["product.product"].create(
            {
                "name": "test6",
            }
        )
        vendor = self.env["res.partner"].create(
            {
                "name": "vendor6",
            }
        )
        supplier_info = self.env["product.supplierinfo"].create(
            {
                "product_id": product.id,
                "partner_id": vendor.id,
            }
        )

        line1 = (
            0,
            0,
            {
                "product_id": product2.id,
                "product_uom_id": product2.uom_id.id,
                "price_unit": 41,
                "product_qty": 10,
            },
        )
        agreement_blanket = self.env["purchase.agreement"].create(
            {
                "line_ids": [line1],
                "agreement_type": "blanket_order",
                "partner_id": vendor.id,
            }
        )
        agreement_blanket.action_confirm()
        self.env["purchase.agreement.line"].create(
            {
                "product_id": product.id,
                "product_qty": 14.0,
                "agreement_id": agreement_blanket.id,
                "price_unit": 10,
            }
        )
        new_si = (
            self.env["product.supplierinfo"].search(
                [("product_id", "=", product.id), ("partner_id", "=", vendor.id)]
            )
            - supplier_info
        )
        self.assertEqual(
            new_si.agreement_id,
            agreement_blanket,
            "the blanket order is not linked to the supplier info",
        )

    def test_08_purchase_agreement_sequence(self):
        new_company = self.env["res.company"].create({"name": "Company 2"})
        self.env["ir.sequence"].create(
            {
                "code": "purchase.agreement.blanket.order",
                "prefix": "REQ_",
                "name": "Blanket Order sequence",
                "company_id": new_company.id,
            }
        )
        self.bo_agreement.company_id = new_company
        self.bo_agreement.line_ids.write({"price_unit": 10.0})
        self.bo_agreement.action_confirm()
        self.assertTrue(self.bo_agreement.name.startswith("REQ_"))

    def test_blanket_order_validity_reaches_the_supplierinfo(self):
        agreement = self.env["purchase.agreement"].create(
            {
                "partner_id": self.res_partner_1.id,
                "agreement_type": "blanket_order",
                "date_start": fields.Date.today() - timedelta(days=60),
                "date_end": fields.Date.today() + timedelta(days=60),
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_09.id,
                            "product_uom_id": self.product_uom_id.id,
                            "product_qty": 100.0,
                            "price_unit": 42.0,
                        }
                    )
                ],
            }
        )
        agreement.action_confirm()

        supplierinfo = agreement.line_ids.supplier_info_ids
        self.assertEqual(len(supplierinfo), 1)
        self.assertEqual(supplierinfo.date_start, agreement.date_start)
        self.assertEqual(supplierinfo.date_end, agreement.date_end)

    def test_expired_blanket_order_does_not_price_anything(self):
        agreement = self.env["purchase.agreement"].create(
            {
                "partner_id": self.res_partner_1.id,
                "agreement_type": "blanket_order",
                "date_start": fields.Date.today() - timedelta(days=60),
                "date_end": fields.Date.today() - timedelta(days=1),
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_09.id,
                            "product_uom_id": self.product_uom_id.id,
                            "product_qty": 100.0,
                            "price_unit": 42.0,
                        }
                    )
                ],
            }
        )
        agreement.action_confirm()

        seller = self.product_09._select_seller(
            partner_id=self.res_partner_1,
            quantity=1.0,
            date=fields.Date.today(),
        )
        self.assertFalse(
            seller,
            "An agreement whose end date has passed must price nothing. Before the "
            "validity window reached product.supplierinfo it kept pricing forever, "
            "including unattended replenishment through stock.rule.",
        )

    def test_line_added_to_a_confirmed_blanket_order_without_a_price(self):
        agreement = self.env["purchase.agreement"].create(
            {
                "partner_id": self.res_partner_1.id,
                "agreement_type": "blanket_order",
                "date_start": fields.Date.today(),
                "date_end": fields.Date.today() + timedelta(days=30),
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_09.id,
                            "product_uom_id": self.product_uom_id.id,
                            "product_qty": 10.0,
                            "price_unit": 5.0,
                        }
                    )
                ],
            }
        )
        agreement.action_confirm()

        with self.assertRaises(UserError):
            self.env["purchase.agreement.line"].create(
                {
                    "agreement_id": agreement.id,
                    "product_id": self.product_13.id,
                    "product_uom_id": self.product_uom_id.id,
                    "product_qty": 5.0,
                }
            )

    def test_description_variants_reach_the_order_line_on_both_paths(self):
        agreement = self.env["purchase.agreement"].create(
            {
                "partner_id": self.res_partner_1.id,
                "agreement_type": "blanket_order",
                "date_start": fields.Date.today(),
                "date_end": fields.Date.today() + timedelta(days=30),
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_09.id,
                            "product_uom_id": self.product_uom_id.id,
                            "product_qty": 100.0,
                            "price_unit": 42.0,
                            "product_description_variants": "ENGRAVED",
                        }
                    )
                ],
            }
        )
        agreement.action_confirm()

        order = self.env["purchase.order"].create(
            {
                "partner_id": self.res_partner_1.id,
                "agreement_id": agreement.id,
                "line_ids": [
                    Command.create(
                        {"product_id": self.product_09.id, "product_qty": 5.0}
                    )
                ],
            }
        )
        self.assertIn(
            "ENGRAVED",
            order.line_ids.name,
            "The append lived only in the onchange path once the compute override "
            "that carried it lost its hook.",
        )

        with Form(
            self.env["purchase.order"].with_context(default_agreement_id=agreement.id)
        ) as order_form:
            order_from_ui = order_form.save()
        self.assertIn("ENGRAVED", order_from_ui.line_ids[0].name)

    def test_purchase_agreement_with_same_product(self):
        self.bo_agreement.partner_id = self.res_partner_1
        agreement_2 = self.bo_agreement.copy({"name": "agreement_2"})
        po_form = Form(
            self.env["purchase.order"].with_context(default_agreement_id=agreement_2.id)
        )
        po = po_form.save()
        self.assertEqual(po.agreement_id, agreement_2)
        po.line_ids.product_qty = 10
        po.action_confirm()
        self.assertEqual(po.state, "done")
        self.assertEqual(self.bo_agreement.line_ids.qty_ordered, 0)
        self.assertEqual(agreement_2.line_ids.qty_ordered, 10)

    def test_purchase_order_taxes_from_purchase_agreement_in_child_company(self):
        child_company = self.env["res.company"].create(
            {
                "name": "My Branch",
                "parent_id": self.env.company.id,
            }
        )
        self.product_09.supplier_taxes_id = self.env["account.tax"].create(
            {
                "name": "Test Tax 10%",
                "amount_type": "percent",
                "amount": 10.0,
                "type_tax_use": "purchase",
                "company_ids": [Command.set(self.env.company.ids)],
            }
        )

        purchase_agreement = (
            self.env["purchase.agreement"]
            .with_company(child_company.id)
            .create(
                {
                    "partner_id": self.res_partner_1.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product_09.id,
                                "product_qty": 5.0,
                                "price_unit": 20,
                            }
                        ),
                    ],
                }
            )
        )
        purchase_agreement.action_confirm()

        po_form = Form(self.env["purchase.order"].with_company(child_company.id))
        po_form.agreement_id = purchase_agreement
        po = po_form.save()
        self.assertEqual(
            po.partner_id,
            purchase_agreement.partner_id,
            "The partner should have been set from the purchase agreement",
        )
        self.assertEqual(
            po.line_ids.price_unit,
            purchase_agreement.line_ids.price_unit,
            "The unit price should have been set from the purchase agreement",
        )
        self.assertEqual(
            po.line_ids.tax_ids,
            purchase_agreement.line_ids.product_id.supplier_taxes_id,
            "The blanket order taxes should have been set",
        )

    def test_a_blocking_agreement_refuses_a_purchase_beyond_it(self):
        self.bo_agreement.write(
            {"partner_id": self.res_partner_1.id, "overrelease_policy": "block"}
        )
        self.bo_agreement.line_ids.price_unit = 10.0
        self.bo_agreement.action_confirm()
        committed = self.bo_agreement.line_ids.product_qty
        po_form = Form(
            self.env["purchase.order"].with_context(
                default_agreement_id=self.bo_agreement.id
            )
        )
        po = po_form.save()
        po.line_ids.product_qty = committed + 1

        self.assertEqual(po.line_ids.agreement_line_id, self.bo_agreement.line_ids)
        with self.assertRaisesRegex(UserError, "goes beyond its agreement"):
            po.action_confirm()

        po.line_ids.product_qty = committed
        po.action_confirm()
        self.assertEqual(self.bo_agreement.line_ids.qty_remaining, 0.0)

    def _blanket_with_break(self):
        agreement = self.env["purchase.agreement"].create(
            {
                "partner_id": self.res_partner_1.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_09.id,
                            "product_uom_id": self.product_uom_id.id,
                            "product_qty": 200.0,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )
        agreement.break_ids = [
            Command.create(
                {"line_id": agreement.line_ids.id, "min_qty": 50.0, "price_unit": 8.0}
            )
        ]
        agreement.action_confirm()
        return agreement

    def _price_for(self, agreement, qty):
        po_form = Form(
            self.env["purchase.order"].with_context(default_agreement_id=agreement.id)
        )
        with po_form.line_ids.edit(0) as line:
            line.product_qty = qty
        return po_form.save().line_ids.price_unit

    def test_a_quantity_break_prices_the_larger_order(self):
        agreement = self._blanket_with_break()

        self.assertRecordValues(
            agreement.line_ids.supplier_info_ids.sorted("min_qty"),
            [{"min_qty": 0.0, "price": 10.0}, {"min_qty": 50.0, "price": 8.0}],
        )
        self.assertEqual(self._price_for(agreement, 30.0), 10.0)
        self.assertEqual(self._price_for(agreement, 60.0), 8.0)

    def test_a_buyer_reprices_a_break_of_a_confirmed_blanket_order(self):
        agreement = self._blanket_with_break()

        agreement.break_ids.with_user(
            self.user_purchase_agreement_user
        ).price_unit = 7.5
        agreement.line_ids.with_user(self.user_purchase_agreement_user).price_unit = 9.0

        self.assertRecordValues(
            agreement.line_ids.supplier_info_ids.sorted("min_qty"),
            [{"min_qty": 0.0, "price": 9.0}, {"min_qty": 50.0, "price": 7.5}],
        )

    def test_a_category_line_discounts_the_vendor_price(self):
        category = self.env["product.category"].create({"name": "Fertilizers"})
        product = self.env["product.product"].create(
            {"name": "Urea", "categ_id": category.id, "purchase_ok": True}
        )
        self.env["product.supplierinfo"].create(
            {
                "partner_id": self.res_partner_1.id,
                "product_tmpl_id": product.product_tmpl_id.id,
                "price": 20.0,
            }
        )
        agreement = self.env["purchase.agreement"].create(
            {
                "partner_id": self.res_partner_1.id,
                "line_ids": [
                    Command.create(
                        {"product_category_id": category.id, "discount": 10.0}
                    )
                ],
            }
        )
        agreement.action_confirm()
        self.assertFalse(agreement.line_ids.supplier_info_ids)

        po_form = Form(
            self.env["purchase.order"].with_context(default_agreement_id=agreement.id)
        )
        with po_form.line_ids.new() as line:
            line.product_id = product
            line.product_qty = 5.0
        order = po_form.save()

        self.assertRecordValues(
            order.line_ids,
            [
                {
                    "price_unit": 20.0,
                    "discount": 10.0,
                    "agreement_line_id": agreement.line_ids.id,
                }
            ],
        )

    def test_an_agreement_with_a_contact_projects_onto_the_company(self):
        vendor = self.env["res.partner"].create(
            {"name": "Seed House", "is_company": True}
        )
        contact = self.env["res.partner"].create(
            {"name": "Seed House, sales desk", "parent_id": vendor.id}
        )
        agreement = self.env["purchase.agreement"].create(
            {
                "partner_id": contact.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_09.id,
                            "product_uom_id": self.product_uom_id.id,
                            "product_qty": 100.0,
                            "price_unit": 33.0,
                        }
                    )
                ],
            }
        )
        agreement.action_confirm()

        self.assertEqual(agreement.line_ids.supplier_info_ids.partner_id, vendor)
        po_form = Form(
            self.env["purchase.order"].with_context(default_agreement_id=agreement.id)
        )
        with po_form.line_ids.edit(0) as line:
            line.product_qty = 2.0
        order = po_form.save()

        self.assertEqual(order.partner_id, contact)
        self.assertEqual(order.line_ids.price_unit, 33.0)
        self.assertFalse(order._get_agreement_breaches())
