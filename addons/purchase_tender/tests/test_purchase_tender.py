from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form
from odoo.tests.common import tagged

from odoo.addons.purchase_tender.tests.common import TestPurchaseTenderCommon


@tagged("post_install", "-at_install")
class TestPurchaseTender(TestPurchaseTenderCommon):
    def test_07_alternative_purchases_wizards(self):
        orig_po = self.env["purchase.order"].create(
            {
                "partner_id": self.res_partner_1.id,
            }
        )
        unit_price = 50
        po_form = Form(orig_po)
        with po_form.line_ids.new() as line:
            line.product_id = self.product_09
            line.product_qty = 5.0
            line.price_unit = unit_price
            line.product_uom_id = self.env.ref("base.product_uom_dozen")
        with po_form.line_ids.new() as line:
            line.display_type = "line_section"
            line.name = "Products"
        with po_form.line_ids.new() as line:
            line.display_type = "line_note"
            line.name = "note1"
        po_form.save()

        action = orig_po.action_invite_counterparties()
        alt_po_wiz = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wiz.partner_ids = self.res_partner_1
        alt_po_wiz.copy_products = True
        alt_po_wiz = alt_po_wiz.save()
        alt_po_wiz.action_invite()
        self.assertEqual(
            len(orig_po.alternative_po_ids),
            2,
            "Original PO should be auto-linked to itself and newly created PO",
        )

        alt_po_1 = orig_po.alternative_po_ids.filtered(lambda po: po.id != orig_po.id)
        self.assertEqual(len(alt_po_1.line_ids), 3)
        self.assertEqual(
            orig_po.line_ids[0].product_id,
            alt_po_1.line_ids[0].product_id,
            "Alternative PO should have copied the product to purchase from original PO",
        )
        self.assertEqual(
            orig_po.line_ids[0].product_qty,
            alt_po_1.line_ids[0].product_qty,
            "Alternative PO should have copied the qty to purchase from original PO",
        )
        self.assertEqual(
            orig_po.line_ids[0].product_uom_id,
            alt_po_1.line_ids[0].product_uom_id,
            "Alternative PO should have copied the product unit of measure from original PO",
        )
        self.assertEqual(
            (orig_po.line_ids[1].display_type, orig_po.line_ids[1].name),
            (alt_po_1.line_ids[1].display_type, alt_po_1.line_ids[1].name),
        )
        self.assertEqual(
            (orig_po.line_ids[2].display_type, orig_po.line_ids[2].name),
            (alt_po_1.line_ids[2].display_type, alt_po_1.line_ids[2].name),
        )
        self.assertEqual(
            len(alt_po_1.alternative_po_ids),
            2,
            "Newly created PO should be auto-linked to itself and original PO",
        )

        alt_po_1.line_ids[0].date_commitment += timedelta(days=1)
        alt_po_1.line_ids[0].price_unit = unit_price - 10
        action = orig_po.action_compare_alternative_lines()
        best_price_ids, best_date_ids, best_price_unit_ids = (
            orig_po.get_tender_best_lines()
        )
        best_price_pol = self.env["purchase.order.line"].browse(best_price_ids)
        best_date_pol = self.env["purchase.order.line"].browse(best_date_ids)
        best_unit_price_pol = self.env["purchase.order.line"].browse(
            best_price_unit_ids
        )
        self.assertEqual(
            best_price_pol.order_id.id,
            alt_po_1.id,
            "Best price PO line was not correctly calculated",
        )
        self.assertEqual(
            best_date_pol.order_id.id,
            orig_po.id,
            "Best date PO line was not correctly calculated",
        )
        self.assertEqual(
            best_unit_price_pol.order_id.id,
            alt_po_1.id,
            "Best unit price PO line was not correctly calculated",
        )

        action = orig_po.action_invite_counterparties()
        alt_po_wiz = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wiz.partner_ids = self.res_partner_1
        alt_po_wiz.copy_products = True
        alt_po_wiz = alt_po_wiz.save()
        alt_po_wiz.action_invite()
        self.assertEqual(
            len(orig_po.alternative_po_ids),
            3,
            "Original PO should be auto-linked to newly created alternative PO",
        )
        self.assertEqual(
            len(alt_po_1.alternative_po_ids),
            3,
            "Alternative PO should be auto-linked to newly created alternative PO",
        )
        alt_po_2 = orig_po.alternative_po_ids.filtered(
            lambda po: po.id not in [alt_po_1.id, orig_po.id]
        )
        self.assertEqual(
            len(alt_po_2.alternative_po_ids),
            3,
            "All alternative POs should be auto-linked to each other",
        )

        alt_po_2.write({"state": "done"})
        action = orig_po.action_confirm()
        warning_wiz = Form(
            self.env["wizard.purchase.order.confirm.open.rival"].with_context(
                **action["context"]
            )
        )
        warning_wiz = warning_wiz.save()
        self.assertEqual(
            len(warning_wiz.rival_ids),
            1,
            "POs not in a RFQ status should not be listed as possible to cancel",
        )
        warning_wiz.action_reject_rivals()
        self.assertEqual(
            alt_po_1.state, "cancel", "Alternative PO should have been cancelled"
        )
        self.assertEqual(
            alt_po_1.outcome,
            "rejected",
            "A losing alternative is rejected by us, not withdrawn",
        )
        self.assertEqual(
            orig_po.state, "done", "Original PO should have been confirmed"
        )

    def test_08_purchases_multi_linkages(self):
        pos = []
        for _ in range(5):
            pos += (
                self.env["purchase.order"]
                .create(
                    {
                        "partner_id": self.res_partner_1.id,
                    }
                )
                .ids
            )
        pos = self.env["purchase.order"].browse(pos)
        po_1, po_2, po_3, po_4, po_5 = pos

        po_1.alternative_po_ids |= po_2
        po_3.alternative_po_ids |= po_4
        groups = self.env["purchase.tender"].search([("order_ids", "in", pos.ids)])
        self.assertEqual(
            len(po_1.alternative_po_ids),
            2,
            "PO1 and PO2 should only be linked to each other",
        )
        self.assertEqual(
            len(po_3.alternative_po_ids),
            2,
            "PO3 and PO4 should only be linked to each other",
        )
        self.assertEqual(
            len(groups), 2, "There should only be 2 groups: (PO1,PO2) and (PO3,PO4)"
        )

        po_5.alternative_po_ids |= po_4
        groups = self.env["purchase.tender"].search([("order_ids", "in", pos.ids)])
        self.assertEqual(
            len(po_3.alternative_po_ids), 3, "PO3 should now be linked to PO4 and PO5"
        )
        self.assertEqual(
            len(po_4.alternative_po_ids), 3, "PO4 should now be linked to PO3 and PO5"
        )
        self.assertEqual(
            len(po_5.alternative_po_ids), 3, "PO5 should now be linked to PO3 and PO4"
        )
        self.assertEqual(
            len(groups), 2, "There should only be 2 groups: (PO1,PO2) and (PO3,PO4,PO5)"
        )

        po_5.alternative_po_ids |= po_1
        groups = self.env["purchase.tender"].search([("order_ids", "in", pos.ids)])
        self.assertEqual(
            len(po_1.alternative_po_ids),
            5,
            "All 5 POs should be linked to each other now",
        )
        self.assertEqual(
            len(groups),
            1,
            "There should only be 1 group containing all 5 POs (other group should have auto-deleted",
        )

        (pos - po_5).alternative_po_ids = [Command.clear()]
        groups = self.env["purchase.tender"].search([("order_ids", "in", pos.ids)])
        self.assertEqual(
            po_5.alternative_po_ids,
            po_5,
            "Unlinked from every other offer, the last PO stays alone in its tender",
        )
        self.assertEqual(len(groups), 1, "The tender itself is a document and stays")

    def test_09_alternative_po_line_price_unit(self):
        po_form = Form(self.env["purchase.order"])
        po_form.partner_id = self.res_partner_1
        with po_form.line_ids.new() as line:
            line.product_id = self.product_09
            line.product_qty = 1
            line.price_unit = 16
        po_1 = po_form.save()

        action = po_1.action_invite_counterparties()
        alt_po_wizard_form = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wizard_form.partner_ids = self.res_partner_1
        alt_po_wizard_form.copy_products = True
        alt_po_wizard = alt_po_wizard_form.save()
        alt_po_wizard.action_invite()

        po_2 = po_1.alternative_po_ids - po_1
        po_2.line_ids.price_unit = 12
        po_2.line_ids.action_award_line()

        self.assertEqual(po_2.line_ids.qty_awarded, 1)
        self.assertEqual(
            po_1.line_ids.qty_awarded,
            0,
            "Awarding a rival's line leaves this one unawarded",
        )
        self.assertEqual(
            po_1.line_ids.product_qty,
            1,
            "Awarding is not destructive: the losing offer keeps its quantity",
        )

        po_1.tender_id.action_award()

        self.assertEqual(po_2.state, "done")
        self.assertRecordValues(po_1, [{"state": "cancel", "outcome": "rejected"}])
        self.assertEqual(po_1.tender_id.state, "awarded")

    def test_10_alternative_po_line_price_unit_different_uom(self):
        po_form = Form(self.env["purchase.order"])
        self.product_09.standard_price = 10
        po_form.partner_id = self.res_partner_1
        with po_form.line_ids.new() as line:
            line.product_id = self.product_09
            line.product_qty = 1
            line.product_uom_id = self.env.ref("base.product_uom_dozen")
        po_1 = po_form.save()
        self.assertEqual(po_1.line_ids[0].price_unit, 120)

        action = po_1.action_invite_counterparties()
        alt_po_wizard_form = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wizard_form.partner_ids = self.res_partner_1
        alt_po_wizard_form.copy_products = True
        alt_po_wizard = alt_po_wizard_form.save()
        alt_po_wizard.action_invite()

        po_2 = po_1.alternative_po_ids - po_1
        self.assertEqual(
            po_2.line_ids[0].product_uom_id, po_1.line_ids[0].product_uom_id
        )
        self.assertEqual(po_2.line_ids[0].price_unit, 120)

    def test_12_alternative_po_line_different_currency(self):
        currency_eur = self.env.ref("base.EUR")
        currency_usd = self.env.ref("base.USD")
        (currency_usd | currency_eur).active = True

        self.env.ref("base.main_company").currency_id = currency_usd

        self.env["res.currency.rate"].create(
            [
                {
                    "name": fields.Datetime.today(),
                    "currency_id": self.env.ref("base.USD").id,
                    "rate": 1,
                },
                {
                    "name": fields.Datetime.today(),
                    "currency_id": self.env.ref("base.EUR").id,
                    "rate": 0.5,
                },
            ]
        )
        vendor_usd = self.env["res.partner"].create(
            {
                "name": "Supplier A",
            }
        )
        vendor_eur = self.env["res.partner"].create(
            {
                "name": "Supplier B",
            }
        )

        product = self.env["product.product"].create(
            {
                "name": "Product",
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": vendor_usd.id,
                            "price": 100,
                            "currency_id": currency_usd.id,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": vendor_eur.id,
                            "price": 80,
                            "currency_id": currency_eur.id,
                        },
                    ),
                ],
            }
        )
        po_form = Form(self.env["purchase.order"])
        po_form.partner_id = vendor_eur
        po_form.currency_id = currency_eur
        with po_form.line_ids.new() as line:
            line.product_id = product
            line.product_qty = 1
        po_orig = po_form.save()
        self.assertEqual(po_orig.line_ids.price_unit, 80)
        self.assertEqual(po_orig.currency_id, currency_eur)

        action = po_orig.action_invite_counterparties()
        alt_po_wizard_form = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wizard_form.partner_ids = vendor_usd
        alt_po_wizard_form.copy_products = True
        alt_po_wizard = alt_po_wizard_form.save()
        alt_po_wizard.action_invite()

        po_alt = po_orig.alternative_po_ids - po_orig
        self.assertEqual(po_alt.currency_id, currency_usd)
        self.assertEqual(po_alt.line_ids.price_unit, 100)

        best_price_ids, best_date_ids, best_price_unit_ids = (
            po_orig.get_tender_best_lines()
        )
        self.assertEqual(len(best_price_ids), 1)
        self.assertEqual(len(best_date_ids), 2)
        self.assertEqual(len(best_price_unit_ids), 1)
        self.assertEqual(best_price_ids[0], po_alt.line_ids.id)
        self.assertEqual(best_price_unit_ids[0], po_alt.line_ids.id)

    def test_alternative_po_with_multiple_price_list(self):
        vendor_a = self.env["res.partner"].create(
            {
                "name": "Supplier A",
            }
        )
        vendor_b = self.env["res.partner"].create(
            {
                "name": "Supplier B",
            }
        )
        product = self.env["product.product"].create(
            {
                "name": "Product",
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": vendor_a.id,
                            "price": 5,
                            "product_code": "code A",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": vendor_b.id,
                            "price": 4,
                            "min_qty": 10,
                            "product_code": "code B",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": vendor_b.id,
                            "price": 6,
                            "min_qty": 1,
                        },
                    ),
                ],
            }
        )
        po_form = Form(self.env["purchase.order"])
        po_form.partner_id = vendor_a
        with po_form.line_ids.new() as line:
            line.product_id = product
            line.product_qty = 100
        po_orig = po_form.save()
        self.assertEqual(po_orig.line_ids.price_unit, 5)
        self.assertEqual(po_orig.line_ids.name, "[code A] Product")
        action = po_orig.action_invite_counterparties()
        alt_po_wizard_form = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wizard_form.partner_ids = vendor_b
        alt_po_wizard_form.copy_products = True
        alt_po_wizard = alt_po_wizard_form.save()
        alt_po_wizard.action_invite()
        po_alt = po_orig.alternative_po_ids - po_orig
        self.assertEqual(po_alt.line_ids.price_unit, 4)
        self.assertEqual(po_alt.line_ids.name, "[code B] Product")

    def test_alternative_purchase_orders_with_vendor_specific_details(self):

        vendor_a = self.env["res.partner"].create({"name": "Supplier A"})
        vendor_b = self.env["res.partner"].create({"name": "Supplier B"})
        vendor_c = self.env["res.partner"].create({"name": "Supplier C"})
        vendor_d = self.env["res.partner"].create({"name": "Supplier D"})

        product = self.env["product.product"].create(
            {
                "name": "Product",
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": vendor_a.id,
                            "price": 5,
                            "product_name": "Custom Name A",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": vendor_b.id,
                            "price": 4,
                            "min_qty": 10,
                            "product_name": "Custom Name B",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": vendor_b.id,
                            "price": 6,
                            "min_qty": 1,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": vendor_c.id,
                            "price": 7,
                            "min_qty": 10,
                            "product_code": "Code C",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": vendor_c.id,
                            "price": 8,
                            "min_qty": 1,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "partner_id": vendor_d.id,
                            "price": 9,
                            "min_qty": 1,
                        },
                    ),
                ],
            }
        )

        po_form = Form(self.env["purchase.order"])
        po_form.partner_id = vendor_a
        with po_form.line_ids.new() as line:
            line.product_id = product
            line.product_qty = 100
        po_orig = po_form.save()
        self.assertEqual(po_orig.line_ids.name, "Custom Name A")

        action = po_orig.action_invite_counterparties()
        alt_po_wizard_form = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wizard_form.partner_ids = vendor_b
        alt_po_wizard_form.copy_products = True
        alt_po_wizard = alt_po_wizard_form.save()
        alt_po_wizard.action_invite()
        po_alt_b = po_orig.alternative_po_ids - po_orig
        self.assertEqual(po_alt_b.line_ids.name, "Custom Name B")

        action = po_orig.action_invite_counterparties()
        alt_po_wizard_form = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wizard_form.partner_ids = vendor_c
        alt_po_wizard_form.copy_products = True
        alt_po_wizard = alt_po_wizard_form.save()
        alt_po_wizard.action_invite()
        po_alt_c = po_orig.alternative_po_ids - po_orig - po_alt_b
        self.assertEqual(po_alt_c.line_ids.name, "[Code C] Product")

        po_form = Form(self.env["purchase.order"])
        po_form.partner_id = vendor_a
        with po_form.line_ids.new() as line:
            line.product_id = product
            line.product_qty = 1
        po_single_qty = po_form.save()
        self.assertEqual(po_single_qty.line_ids.name, "Custom Name A")

        action = po_single_qty.action_invite_counterparties()
        alt_po_wizard_form = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wizard_form.partner_ids = vendor_c
        alt_po_wizard_form.copy_products = True
        alt_po_wizard = alt_po_wizard_form.save()
        alt_po_wizard.action_invite()
        po_alt_c_single_qty = po_single_qty.alternative_po_ids - po_single_qty
        self.assertEqual(po_alt_c_single_qty.line_ids.name, "Product")

        action = po_single_qty.action_invite_counterparties()
        alt_po_wizard_form = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wizard_form.partner_ids = vendor_d
        alt_po_wizard_form.copy_products = True
        alt_po_wizard = alt_po_wizard_form.save()
        alt_po_wizard.action_invite()
        po_alt_d_single_qty = (
            po_single_qty.alternative_po_ids - po_single_qty - po_alt_c_single_qty
        )
        self.assertEqual(po_alt_d_single_qty.line_ids.name, "Custom Name A")

    def test_taxes_for_alternative_po(self):
        product = self.product_13
        vendor = self.res_partner_1
        po_form = Form(self.env["purchase.order"])
        po_form.partner_id = vendor
        with po_form.line_ids.new() as line:
            line.product_id = product
            line.product_qty = 1
        orig_po = po_form.save()
        action = orig_po.action_invite_counterparties()
        alt_po_wizard_form = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wizard_form.partner_ids = vendor
        alt_po_wizard_form.copy_products = True
        alt_po_wizard = alt_po_wizard_form.save()
        alt_po_id = alt_po_wizard.action_invite()["res_id"]
        alt_po = self.env["purchase.order"].browse(alt_po_id)
        self.assertEqual(orig_po.line_ids.tax_ids, alt_po.line_ids.tax_ids)

    def test_alternative_purchase_order_merge(self):
        po_1 = Form(self.env["purchase.order"])
        res_partner_2 = self.env["res.partner"].create({"name": "Vendor 2"})
        res_partner_3 = self.env["res.partner"].create({"name": "Vendor 3"})
        po_1.partner_id = self.res_partner_1
        with po_1.line_ids.new() as po_line:
            po_line.product_id = self.product_09
            po_line.product_qty = 1
            po_line.price_unit = 100
        po_1 = po_1.save()

        action = po_1.action_invite_counterparties()
        alt_po_wiz = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wiz.partner_ids = res_partner_2
        alt_po_wiz.copy_products = True
        alt_po_wiz = alt_po_wiz.save()
        alt_po_wiz.action_invite()
        po_2 = Form(self.env["purchase.order"])
        po_2.partner_id = res_partner_3
        with po_2.line_ids.new() as po_line_1:
            po_line_1.product_id = self.product_09
            po_line_1.product_qty = 5
            po_line_1.price_unit = 100
        po_2 = po_2.save()

        action = po_2.action_invite_counterparties()
        alt_po_wiz = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        alt_po_wiz.partner_ids = res_partner_2
        alt_po_wiz.copy_products = True
        alt_po_wiz = alt_po_wiz.save()
        alt_po_wiz.action_invite()
        po_orders = self.env["purchase.order"].search(
            [("partner_id", "=", res_partner_2.id)]
        )
        merger_alternative_orders = po_orders[0] | po_orders[1]
        merger_alternative_orders.action_merge()
        self.assertEqual(len(po_orders[0].alternative_po_ids), 4)

    def test_create_alternatives_for_multiple_vendors(self):
        res_partner_2 = self.env["res.partner"].create({"name": "Vendor 2"})
        res_partner_3 = self.env["res.partner"].create({"name": "Vendor 3"})
        res_partner_4 = self.env["res.partner"].create({"name": "Vendor 4"})
        orig_po = self.env["purchase.order"].create(
            {
                "partner_id": self.res_partner_1.id,
            }
        )

        po_form = Form(orig_po)
        with po_form.line_ids.new() as line:
            line.product_id = self.product_09
            line.product_qty = 5.0
        po_form.save()

        alt_po_wiz = Form.from_action(self.env, orig_po.action_invite_counterparties())
        alt_po_wiz.partner_ids = res_partner_2 | res_partner_3 | res_partner_4
        alt_po_wiz = alt_po_wiz.save()
        alt_po_wiz.action_invite()
        self.assertEqual(
            len(orig_po.alternative_po_ids),
            4,
            "There should be exactly 4 linked PO's: 1 original + 3 alternatives (one for each selected vendor.)",
        )

    def test_alternative_purchase_vendor_currency(self):
        currency_eur = self.env.ref("base.EUR")
        currency_usd = self.env.ref("base.USD")

        self.res_partner_1.write({"property_purchase_currency_id": currency_usd.id})
        res_partner_2 = self.env["res.partner"].create(
            {"name": "Vendor 2", "property_purchase_currency_id": currency_eur.id}
        )

        orig_po = self.env["purchase.order"].create(
            {
                "partner_id": self.res_partner_1.id,
            }
        )
        po_form = Form(orig_po)
        with po_form.line_ids.new() as line:
            line.product_id = self.product_09
            line.product_qty = 1.0
        po_form.save()

        self.assertEqual(
            orig_po.currency_id,
            self.res_partner_1.property_purchase_currency_id,
            "The original PO currency should match with the vendor purchase currency (USD).",
        )

        alt_po_wiz = Form.from_action(self.env, orig_po.action_invite_counterparties())
        alt_po_wiz.partner_ids = res_partner_2
        alt_po_wizard = alt_po_wiz.save()
        alt_po_wizard.action_invite()
        alt_po = orig_po.alternative_po_ids.filtered(
            lambda po: po.partner_id == res_partner_2
        )

        self.assertEqual(
            alt_po.currency_id,
            res_partner_2.property_purchase_currency_id,
            "The alternative PO currency should match with vendor 2 purchase currency (EUR).",
        )

    def test_payment_terms_for_alternative_rfq(self):
        pay_terms_immediate = self.env.ref(
            "payment_term.account_payment_term_immediate"
        )
        pay_terms_end_month = self.env.ref(
            "payment_term.account_payment_term_end_following_month"
        )

        self.res_partner_1.write(
            {"property_supplier_payment_term_id": pay_terms_immediate.id}
        )
        vendor_b = self.env["res.partner"].create(
            {
                "name": "Supplier B",
                "property_supplier_payment_term_id": pay_terms_end_month.id,
            }
        )

        po_form = Form(self.env["purchase.order"])
        po_form.partner_id = self.res_partner_1
        with po_form.line_ids.new() as line:
            line.product_id = self.product_13
            line.product_qty = 1
        orig_po = po_form.save()

        self.assertEqual(
            orig_po.payment_term_id,
            orig_po.partner_id.property_supplier_payment_term_id,
        )

        alt_po_wizard_form = Form.from_action(
            self.env, orig_po.action_invite_counterparties()
        )
        alt_po_wizard_form.partner_ids = vendor_b
        alt_po_wizard = alt_po_wizard_form.save()
        alt_po_wizard.action_invite()["res_id"]
        alt_po = orig_po.alternative_po_ids - orig_po

        self.assertEqual(
            alt_po.payment_term_id, alt_po.partner_id.property_supplier_payment_term_id
        )

    def _tender_of_two(self, qty=10.0):
        vendor_b = self.env["res.partner"].create({"name": "Vendor B"})
        po_a = self.env["purchase.order"].create(
            {
                "partner_id": self.res_partner_1.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_09.id,
                            "product_qty": qty,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )
        action = po_a.action_invite_counterparties()
        wizard = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        wizard.partner_ids = vendor_b
        wizard.save().action_invite()
        po_b = po_a.alternative_po_ids - po_a
        po_b.line_ids.price_unit = 8.0
        return po_a, po_b

    def test_inviting_a_vendor_opens_a_numbered_tender(self):
        po_a, po_b = self._tender_of_two()

        tender = po_a.tender_id
        self.assertTrue(tender.name.startswith("TND"))
        self.assertEqual(tender.state, "open")
        self.assertEqual(tender.order_ids, po_a | po_b)
        self.assertEqual(po_b.tender_id, tender)

    def test_the_lowest_offer_is_best_when_we_buy(self):
        po_a, po_b = self._tender_of_two()

        best = po_a.tender_id._get_best_lines()

        self.assertEqual(best["best_total"], po_b.line_ids.ids)
        self.assertEqual(best["best_unit"], po_b.line_ids.ids)

    def test_an_award_can_be_split_between_vendors(self):
        po_a, po_b = self._tender_of_two()
        po_a.line_ids.qty_awarded = 4.0
        po_b.line_ids.qty_awarded = 6.0

        po_a.tender_id.action_award()

        self.assertRecordValues(
            po_a | po_b,
            [
                {"state": "done", "outcome": "won"},
                {"state": "done", "outcome": "won"},
            ],
        )
        self.assertEqual(po_a.line_ids.product_qty, 4.0)
        self.assertEqual(po_b.line_ids.product_qty, 6.0)

    def test_a_tender_is_awarded_only_with_an_award(self):
        po_a, _po_b = self._tender_of_two()

        with self.assertRaisesRegex(UserError, "Award at least one line"):
            po_a.tender_id.action_award()

    def test_invited_offers_ignore_the_origin_forms_defaults(self):
        po_a = self.env["purchase.order"].create({"partner_id": self.res_partner_1.id})
        vendor_b = self.env["res.partner"].create({"name": "Vendor B"})

        action = po_a.with_context(
            default_notes="<p>only for the origin</p>"
        ).action_invite_counterparties()
        wizard = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        wizard.partner_ids = vendor_b
        wizard.save().with_context(
            default_notes="<p>only for the origin</p>"
        ).action_invite()

        offer = po_a.tender_id.order_ids - po_a
        self.assertNotIn("only for the origin", offer.notes or "")

    def test_a_tender_opened_from_an_order_needs_what_it_asks(self):
        po_a, _po_b = self._tender_of_two()

        self.assertRecordValues(
            po_a.tender_id.line_ids,
            [{"product_id": self.product_09.id, "product_qty": 10.0}],
        )

    def test_vendors_are_invited_to_the_tender_needs(self):
        tender = self.env["purchase.tender"].create(
            {
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_09.id,
                            "product_qty": 5.0,
                            "description": "Grade A, 20 kg sacks",
                        }
                    )
                ]
            }
        )
        vendors = self.env["res.partner"].create(
            [{"name": "Vendor N1"}, {"name": "Vendor N2"}]
        )
        action = tender.action_invite()
        wizard = Form(self.env[action["res_model"]].with_context(**action["context"]))
        wizard.partner_ids.add(vendors[0])
        wizard.partner_ids.add(vendors[1])
        wizard.save().action_invite()

        self.assertEqual(tender.order_ids.partner_id, vendors)
        self.assertRecordValues(
            tender.order_ids.line_ids,
            [
                {
                    "product_id": self.product_09.id,
                    "product_qty": 5.0,
                    "name": "Grade A, 20 kg sacks",
                }
            ]
            * 2,
        )

    def test_the_needs_show_what_is_awarded(self):
        po_a, _po_b = self._tender_of_two()
        po_a.line_ids.qty_awarded = 4.0
        need = po_a.tender_id.line_ids

        self.assertRecordValues(
            need, [{"offer_count": 2, "qty_awarded": 4.0, "qty_to_award": 6.0}]
        )

        po_a.tender_id.action_award()

        self.assertRecordValues(need, [{"qty_awarded": 4.0, "qty_to_award": 6.0}])
