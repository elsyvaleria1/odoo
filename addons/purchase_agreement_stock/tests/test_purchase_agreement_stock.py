from datetime import timedelta

from odoo import Command, fields
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.purchase_agreement.tests.common import TestPurchaseAgreementCommon


class ReturnsAgainstAgreement:
    def _received_against_agreement(self, received):
        vendor = self.env["res.partner"].create({"name": "Returns Vendor"})
        product = self.env["product.product"].create(
            {"name": "Returned Crate", "is_storable": True, "standard_price": 10.0}
        )
        agreement = self.env["purchase.agreement"].create(
            {
                "partner_id": vendor.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": 10.0,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )
        agreement.action_confirm()
        order = self.env["purchase.order"].create(
            {
                "partner_id": vendor.id,
                "agreement_id": agreement.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": received,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        receipt = order.picking_ids
        receipt.move_ids.quantity = received
        receipt.move_ids.picked = True
        receipt.button_validate()
        return agreement, order

    def _return(self, order, qty):
        receipt = order.picking_ids
        wizard = Form(
            self.env["wizard.stock.picking.return"].with_context(
                active_ids=receipt.ids,
                active_id=receipt.id,
                active_model="stock.picking",
            )
        ).save()
        wizard.product_return_moves.write({"quantity": qty, "to_refund": True})
        returned = self.env["stock.picking"].browse(
            wizard.action_create_returns()["res_id"]
        )
        returned.move_ids.quantity = qty
        returned.move_ids.picked = True
        returned.button_validate()


class TestPurchaseAgreementStock(ReturnsAgainstAgreement, TestPurchaseAgreementCommon):
    def test_02_purchase_agreement_stock(self):
        unit = self.ref("base.product_uom_unit")
        warehouse1 = self.env.ref("stock.warehouse0")
        route_buy = self.ref("purchase_stock.route_warehouse0_buy")
        route_mto = warehouse1.mto_pull_id.route_id.id
        vendor1 = self.env["res.partner"].create(
            {"name": "AAA", "email": "from.test@example.com"}
        )
        vendor2 = self.env["res.partner"].create(
            {"name": "BBB", "email": "from.test2@example.com"}
        )
        product_test = self.env["product.product"].create(
            {
                "name": "Usb Keyboard",
                "is_storable": True,
                "uom_id": unit,
                "route_ids": [(6, 0, [route_buy, route_mto])],
            }
        )
        supplier_info1 = self.env["product.supplierinfo"].create(
            {
                "product_id": product_test.id,
                "partner_id": vendor1.id,
                "price": 50,
            }
        )

        stock_location = self.env.ref("stock.stock_location_stock")
        customer_location = self.env.ref("stock.stock_location_customers")
        move1 = self.env["stock.move"].create(
            {
                "procure_method": "make_to_order",
                "location_id": stock_location.id,
                "location_dest_id": customer_location.id,
                "product_id": product_test.id,
                "product_uom_id": unit,
                "product_uom_qty": 10.0,
                "price_unit": 10,
            }
        )
        move1._action_confirm()

        purchase1 = self.env["purchase.order"].search([("partner_id", "=", vendor1.id)])
        self.assertEqual(
            purchase1.line_ids.price_unit,
            50,
            "The price on the purchase order is not the supplierinfo one",
        )

        line1 = (
            0,
            0,
            {
                "product_id": product_test.id,
                "product_qty": 18,
                "product_uom_id": product_test.uom_id.id,
                "price_unit": 50,
            },
        )
        agreement_blanket = self.env["purchase.agreement"].create(
            {
                "line_ids": [line1],
                "agreement_type": "blanket_order",
                "partner_id": vendor2.id,
                "currency_id": self.env.user.company_id.currency_id.id,
            }
        )
        agreement_blanket.action_confirm()

        move2 = self.env["stock.move"].create(
            {
                "procure_method": "make_to_order",
                "location_id": stock_location.id,
                "location_dest_id": customer_location.id,
                "product_id": product_test.id,
                "product_uom_id": unit,
                "product_uom_qty": 10.0,
                "price_unit": 10,
            }
        )
        move2._action_confirm()

        self.assertEqual(purchase1.line_ids.product_qty, 20)

        supplier_info1.sequence = 2
        agreement_blanket.line_ids.supplier_info_ids.sequence = 1

        move3 = self.env["stock.move"].create(
            {
                "procure_method": "make_to_order",
                "location_id": stock_location.id,
                "location_dest_id": customer_location.id,
                "product_id": product_test.id,
                "product_uom_id": unit,
                "product_uom_qty": 10.0,
                "price_unit": 10,
            }
        )
        move3._action_confirm()

        purchase2 = self.env["purchase.order"].search(
            [
                ("partner_id", "=", vendor2.id),
                ("agreement_id", "=", agreement_blanket.id),
            ]
        )
        self.assertEqual(len(purchase2), 1)
        self.assertEqual(
            purchase2.line_ids.price_unit,
            50,
            "The price on the purchase order is not the blanquet order one",
        )

    def test_03_purchase_agreement_stock(self):

        unit = self.ref("base.product_uom_unit")
        warehouse1 = self.env.ref("stock.warehouse0")
        route_buy = self.ref("purchase_stock.route_warehouse0_buy")
        route_mto = warehouse1.mto_pull_id.route_id.id
        vendor1 = self.env["res.partner"].create(
            {"name": "AAA", "email": "from.test@example.com"}
        )
        product_1 = self.env["product.product"].create(
            {
                "name": "product1",
                "is_storable": True,
                "uom_id": unit,
                "seller_ids": [
                    Command.create(
                        {
                            "partner_id": vendor1.id,
                            "price": 50,
                        }
                    )
                ],
                "route_ids": [(6, 0, [route_buy, route_mto])],
            }
        )
        product_2 = self.env["product.product"].create(
            {
                "name": "product2",
                "is_storable": True,
                "uom_id": unit,
                "seller_ids": [
                    Command.create(
                        {
                            "partner_id": vendor1.id,
                            "price": 50,
                        }
                    )
                ],
                "route_ids": [(6, 0, [route_buy, route_mto])],
            }
        )

        line1 = (
            0,
            0,
            {
                "product_id": product_1.id,
                "product_qty": 18,
                "product_uom_id": product_1.uom_id.id,
                "price_unit": 41,
            },
        )
        line2 = (
            0,
            0,
            {
                "product_id": product_2.id,
                "product_qty": 18,
                "product_uom_id": product_2.uom_id.id,
                "price_unit": 42,
            },
        )
        agreement_1 = self.env["purchase.agreement"].create(
            {
                "line_ids": [line1],
                "agreement_type": "blanket_order",
                "partner_id": vendor1.id,
                "currency_id": self.env.user.company_id.currency_id.id,
            }
        )
        agreement_2 = self.env["purchase.agreement"].create(
            {
                "line_ids": [line2],
                "agreement_type": "blanket_order",
                "partner_id": vendor1.id,
                "currency_id": self.env.user.company_id.currency_id.id,
            }
        )
        agreement_1.action_confirm()
        agreement_2.action_confirm()
        stock_location = self.env.ref("stock.stock_location_stock")
        customer_location = self.env.ref("stock.stock_location_customers")
        move1 = self.env["stock.move"].create(
            {
                "procure_method": "make_to_order",
                "location_id": stock_location.id,
                "location_dest_id": customer_location.id,
                "product_id": product_1.id,
                "product_uom_id": unit,
                "product_uom_qty": 10.0,
                "price_unit": 100,
            }
        )
        move2 = self.env["stock.move"].create(
            {
                "procure_method": "make_to_order",
                "location_id": stock_location.id,
                "location_dest_id": customer_location.id,
                "product_id": product_2.id,
                "product_uom_id": unit,
                "product_uom_qty": 10.0,
                "price_unit": 100,
            }
        )
        move1._action_confirm()
        move2._action_confirm()
        POL1 = (
            self.env["purchase.order.line"]
            .search([("product_id", "=", product_1.id)])
            .order_id
        )
        POL2 = (
            self.env["purchase.order.line"]
            .search([("product_id", "=", product_2.id)])
            .order_id
        )
        self.assertFalse(
            POL1 == POL2,
            "The two blanket orders should generate two purchase different purchase orders",
        )
        POL1.write(
            {
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": product_2.name,
                            "product_id": product_2.id,
                            "product_qty": 5.0,
                            "product_uom_id": product_2.uom_id.id,
                        },
                    )
                ]
            }
        )
        order_line = self.env["purchase.order.line"].search(
            [
                ("product_id", "=", product_2.id),
                ("product_qty", "=", 5.0),
            ]
        )
        self.assertEqual(
            order_line.price_unit,
            50,
            "The supplier info chosen should be the one without agreement id",
        )

    def _create_expired_blanket_order(self, vendor, product):
        agreement = self.env["purchase.agreement"].create(
            {
                "partner_id": vendor.id,
                "agreement_type": "blanket_order",
                "date_start": fields.Date.today() - timedelta(days=30),
                "date_end": fields.Date.today() - timedelta(days=1),
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": 100.0,
                            "price_unit": 42.0,
                        }
                    )
                ],
            }
        )
        agreement.action_confirm()
        return agreement

    def _run_buy_procurement(self, product, quantity):
        warehouse = self.env.ref("stock.warehouse0")
        route_buy = self.env.ref("purchase_stock.route_warehouse0_buy")
        procurement = self.env["stock.rule"].Procurement(
            product,
            quantity,
            product.uom_id,
            warehouse.lot_stock_id,
            "replenishment",
            "replenishment",
            self.env.company,
            {
                "warehouse_id": warehouse,
                "route_ids": route_buy,
                "date_planned": fields.Datetime.now(),
            },
        )
        self.env["stock.rule"].run([procurement])
        return self.env["purchase.order.line"].search([("product_id", "=", product.id)])

    def _create_bought_product(self):
        route_buy = self.env.ref("purchase_stock.route_warehouse0_buy")
        return self.env["product.product"].create(
            {
                "name": "Contracted part",
                "is_storable": True,
                "standard_price": 7.0,
                "route_ids": [Command.set(route_buy.ids)],
            }
        )

    def test_expired_blanket_order_does_not_capture_replenishment(self):
        vendor = self.env["res.partner"].create({"name": "Agreement vendor"})
        product = self._create_bought_product()
        self._create_expired_blanket_order(vendor, product)

        lines = self._run_buy_procurement(product, 50.0)

        self.assertFalse(
            lines,
            "An expired agreement is the product's only seller, so nothing may be "
            "ordered: the replenishment fallback used to pick the agreement's seller "
            "regardless of its dates and bind a zero-priced RFQ to the expired agreement.",
        )

    def test_replenishment_fallback_skips_an_expired_blanket_order(self):
        agreement_vendor = self.env["res.partner"].create({"name": "Agreement vendor"})
        regular_vendor = self.env["res.partner"].create({"name": "Regular vendor"})
        product = self._create_bought_product()
        self._create_expired_blanket_order(agreement_vendor, product)
        self.env["product.supplierinfo"].create(
            {
                "partner_id": regular_vendor.id,
                "product_tmpl_id": product.product_tmpl_id.id,
                "price": 90.0,
                "date_end": fields.Date.today() - timedelta(days=2),
            }
        )

        lines = self._run_buy_procurement(product, 50.0)

        self.assertEqual(lines.order_id.partner_id, regular_vendor)
        self.assertFalse(lines.order_id.agreement_id)
        self.assertEqual(
            lines.price_unit,
            7.0,
            "No seller is in force, so the line is priced like any purchase line "
            "without one: at product cost.",
        )

    def test_goods_sent_back_go_back_into_the_agreement(self):
        agreement, order = self._received_against_agreement(6.0)
        self.assertEqual(agreement.line_ids.qty_remaining, 4.0)

        self._return(order, 2.0)

        self.assertRecordValues(
            agreement.line_ids,
            [{"qty_ordered": 4.0, "qty_remaining": 6.0, "amount_ordered": 40.0}],
        )


@tagged("post_install", "-at_install")
class TestPurchaseAgreementStockInvoiced(
    ReturnsAgainstAgreement, AccountTestInvoicingCommon
):
    def test_a_return_and_its_credit_note_count_once(self):
        agreement, order = self._received_against_agreement(6.0)
        order.create_invoice()
        bill = order.invoice_ids
        bill.invoice_date = fields.Date.today()
        bill.action_post()
        self._return(order, 2.0)

        refund = bill._reverse_moves()
        refund.invoice_date = fields.Date.today()
        refund.invoice_line_ids.quantity = 2.0
        refund.action_post()

        self.assertEqual(agreement.line_ids.qty_ordered, 4.0)
