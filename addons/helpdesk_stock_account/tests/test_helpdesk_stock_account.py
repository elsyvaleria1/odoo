from odoo import Command
from odoo.tests import Form, tagged

from odoo.addons.helpdesk.tests.common import HelpdeskCommon


@tagged("post_install", "-at_install")
class TestHelpdeskStockAccount(HelpdeskCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_team.helpdesk_use_product_returns = True
        cls.test_team.helpdesk_use_credit_notes = True
        cls.journal_id = (
            cls.env["account.journal"]
            .search(
                [("type", "=", "sale"), ("company_id", "=", cls.main_company_id)],
                limit=1,
            )
            .id
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Test product",
                "is_storable": True,
                "invoice_policy": "ordered",
            }
        )
        cls.ticket = cls.env["helpdesk.ticket"].create(
            {
                "name": "test",
                "partner_id": cls.partner.id,
                "team_id": cls.test_team.id,
            }
        )

    def test_refund_after_return_single_so(self):
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 5,
                        }
                    )
                ],
            }
        )
        sale_order.action_confirm()
        sale_order._create_invoices()
        sale_order.invoice_ids.action_post()
        sale_order.picking_ids.move_ids.quantity = 5
        sale_order.picking_ids.button_validate()
        self.return_product(sale_order, 2)
        refund_move = self.refund_product(
            sale_order.invoice_ids
        )
        self.assertEqual(refund_move.invoice_line_ids.quantity, 2)

    def test_refund_after_return_multi_so(self):
        sale_orders = self.env["sale.order"].create(
            [
                {
                    "partner_id": self.partner.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_qty": 10,
                            }
                        )
                    ],
                },
                {
                    "partner_id": self.partner.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_qty": 5,
                            }
                        )
                    ],
                },
            ]
        )
        sale_orders.action_confirm()
        sale_orders._create_invoices()
        sale_orders.invoice_ids.action_post()
        sale_orders[0].picking_ids.move_ids.quantity = 10
        sale_orders[1].picking_ids.move_ids.quantity = 5
        sale_orders.picking_ids.button_validate()
        self.return_product(sale_orders[0], 2)
        self.return_product(sale_orders[1], 3)
        refund_move = self.refund_product(
            sale_orders.invoice_ids
        )
        self.assertEqual(refund_move.invoice_line_ids[0].quantity, 2)
        self.assertEqual(refund_move.invoice_line_ids[1].quantity, 3)

    def test_refund_after_return_down_payment(self):
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 5,
                        }
                    )
                ],
            }
        )
        sale_order.action_confirm()
        sale_order.picking_ids.move_ids.quantity = 5
        sale_order.picking_ids.button_validate()
        context = {
            "active_model": "sale.order",
            "active_ids": [sale_order.id],
            "active_id": sale_order.id,
        }
        downpayment = (
            self.env["wizard.sale.order.invoice"]
            .with_context(context)
            .create(
                {
                    "advance_payment_method": "fixed",
                    "fixed_amount": 50,
                }
            )
        )
        downpayment.create_invoices()
        payment = self.env["wizard.sale.order.invoice"].with_context(context).create({})
        payment.create_invoices()
        self.return_product(sale_order, 2)
        refund_moves = self.refund_product(
            sale_order.invoice_ids
        )
        refund = refund_moves.filtered(
            lambda move: self.product in move.invoice_line_ids.product_id
        )
        product_line = refund.invoice_line_ids[0]
        down_payment_line = refund.invoice_line_ids[2]
        self.assertEqual(
            product_line.quantity, -8
        )
        self.assertEqual(
            down_payment_line.quantity, 1
        )

    def refund_product(self, invoice):
        credit_note = self.env["wizard.account.move.reverse"].create(
            {
                "helpdesk_ticket_id": self.ticket.id,
                "journal_id": self.journal_id,
                "reason": "test",
                "move_ids": invoice,
                "product_id": self.product.id,
            }
        )
        res = credit_note.refund_moves()
        return self.env["account.move"].browse(res.get("res_id") or res["domain"][0][2])

    def return_product(self, sale_order, qty):
        stock_picking_return = self.env["wizard.stock.picking.return"].create(
            {
                "picking_id": sale_order.picking_ids.id,
            }
        )
        stock_picking_return.product_return_moves.quantity = qty
        return_picking = stock_picking_return._create_return()
        return_picking.move_ids.quantity = qty
        return_picking.button_validate()
        Form(
            self.env["wizard.stock.picking.validate.partial"].with_context(
                {
                    "default_validate_picking_ids": [return_picking.id],
                    "default_pick_ids": [(4, return_picking.id)],
                    "default_show_transfers": False,
                }
            )
        ).save().process()

        return return_picking

    def test_refund_only_one_product(self):
        product_0 = self.env["product.product"].create(
            {
                "name": "Test Product 0",
                "list_price": 10,
            }
        )
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 5,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": product_0.id,
                            "product_qty": 5,
                        }
                    ),
                ],
            }
        )

        sale_order.action_confirm()
        sale_order._create_invoices()
        invoice = sale_order.invoice_ids
        invoice.action_post()
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "test",
                "partner_id": self.partner.id,
                "team_id": self.test_team.id,
                "sale_order_id": sale_order.id,
            }
        )
        credit_note = self.env["wizard.account.move.reverse"].create(
            {
                "helpdesk_ticket_id": ticket.id,
                "journal_id": self.journal_id,
                "reason": "test",
                "move_ids": invoice,
                "product_id": self.product.id,
            }
        )
        credit_note.refund_moves()
        self.assertEqual(
            credit_note.new_move_ids.invoice_line_ids.product_id, self.product
        )
