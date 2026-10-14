from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from odoo.addons.helpdesk.tests import common


@tagged("post_install", "-at_install")
class TestHelpdeskStock(common.HelpdeskCommon):
    def test_helpdesk_stock(self):
        self.test_team.helpdesk_use_product_returns = True

        product = self.env["product.product"].create(
            {
                "name": "product 1",
                "is_storable": True,
                "invoice_policy": "ordered",
            }
        )
        so = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
            }
        )
        self.env["sale.order.line"].create(
            {
                "product_id": product.id,
                "price_unit": 10,
                "product_qty": 1,
                "order_id": so.id,
            }
        )
        so.action_confirm()
        so._create_invoices()
        invoice = so.invoice_ids
        invoice.action_post()
        so.picking_ids[0].move_ids[0].quantity = 1
        so.picking_ids[0].button_validate()
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "test",
                "partner_id": self.partner.id,
                "team_id": self.test_team.id,
                "sale_order_id": so.id,
            }
        )

        stock_picking_form = Form(
            self.env["wizard.stock.picking.return"].with_context(
                {"active_model": "helpdesk.ticket", "default_ticket_id": ticket.id}
            )
        )
        stock_picking_form.picking_id = so.picking_ids[0]
        with stock_picking_form.product_return_moves.edit(0) as line:
            line.quantity = 1
        return_picking = stock_picking_form.save()

        self.assertEqual(
            len(return_picking.product_return_moves),
            1,
            "A picking line should be present",
        )
        self.assertEqual(
            return_picking.product_return_moves[0].product_id,
            product,
            "The product of the picking line does not match the product of the sale order",
        )

        return_picking.action_create_returns()

        return_picking = self.env["stock.picking"].search(
            [
                ("partner_id", "=", self.partner.id),
                ("picking_type_code", "=", "incoming"),
            ]
        )

        self.assertEqual(len(return_picking), 1, "No return created")
        self.assertEqual(return_picking.state, "assigned", "Wrong status of the refund")
        self.assertEqual(
            ticket.pickings_count, 1, "The ticket should be linked to a return"
        )
        self.assertEqual(
            return_picking.id,
            ticket.picking_ids[0].id,
            "The correct return should be referenced in the ticket",
        )

        return_picking.move_ids[0].quantity = 1
        return_picking.button_validate()
        return_picking.state

        last_message = str(ticket.message_ids[0].body)

        self.assertTrue(
            return_picking.display_name in last_message and "Return" in last_message,
            "Return validation should be logged on the ticket",
        )

    def test_helpdesk_stock_return(self):
        product = self.env["product.product"].create(
            {
                "name": "test product",
                "is_storable": True,
                "invoice_policy": "ordered",
            }
        )
        partner = self.env["res.partner"].create({"name": "Customer"})
        so = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
            }
        )
        self.env["sale.order.line"].create(
            {
                "product_id": product.id,
                "price_unit": 10,
                "product_qty": 5,
                "order_id": so.id,
            }
        )
        so.action_confirm()
        delivery_order = so.picking_ids[0]
        delivery_order.move_ids[0].quantity = 3
        delivery_order.button_validate()
        Form(
            self.env["wizard.stock.picking.validate.partial"].with_context(
                {
                    "default_validate_picking_ids": [delivery_order.id],
                    "default_pick_ids": [(4, delivery_order.id)],
                    "default_show_transfers": False,
                }
            )
        ).save().process()
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "test",
                "partner_id": partner.id,
                "team_id": self.test_team.id,
                "sale_order_id": so.id,
            }
        )
        try:
            Form(
                self.env["wizard.stock.picking.return"].with_context(
                    {"active_model": "helpdesk.ticket", "default_ticket_id": ticket.id}
                )
            )
        except UserError:
            self.fail(
                "We should be able to make a return of the already delivered quantities "
                "even if the so has an open backorder that isn't done"
            )

    def test_helpdesk_ticket_partner_has_picking(self):
        product = self.env["product.product"].create(
            {
                "name": "Product 2",
                "is_storable": True,
                "invoice_policy": "ordered",
            }
        )
        commercial_partner = self.env["res.partner"].create(
            {
                "name": "Commercial Customer",
                "is_company": True,
            }
        )
        partner = self.env["res.partner"].create(
            {
                "name": "Customer 2",
                "parent_id": commercial_partner.id,
            }
        )
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "price_unit": 10,
                            "product_qty": 5,
                        }
                    )
                ],
            }
        )
        sale_order.action_confirm()
        delivery_order = sale_order.picking_ids[0]
        delivery_order.move_ids[0].quantity = 5
        delivery_order.button_validate()

        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Test Ticket",
                "partner_id": partner.id,
                "team_id": self.test_team.id,
                "sale_order_id": sale_order.id,
            }
        )

        self.assertTrue(
            ticket.has_partner_picking,
            "The ticket should have a related delivery order for the partner.",
        )

        ticket.partner_id = commercial_partner

        self.assertTrue(
            ticket.has_partner_picking,
            "The ticket should have a related delivery order for the commercial partner",
        )

    def test_helpdesk_ticket_product_from_parent_company(self):
        company_product, employee_1_product, employee_2_product = self.env[
            "product.product"
        ].create(
            [
                {"name": "Company Product"},
                {"name": "Employee 1 Product"},
                {"name": "Employee 2 Product"},
            ]
        )
        partners = self.env["res.partner"].create(
            [
                {"name": "Company", "is_company": True},
                {"name": "Employee 1", "is_company": False},
                {"name": "Employee 1", "is_company": False},
            ]
        )
        company, employee_1, employee_2 = partners
        (employee_1 | employee_2).commercial_partner_id = company

        sale_orders = self.env["sale.order"].create(
            [
                {
                    "partner_id": company.id,
                    "line_ids": [Command.create({"product_id": company_product.id})],
                },
                {
                    "partner_id": employee_1.id,
                    "line_ids": [Command.create({"product_id": employee_1_product.id})],
                },
                {
                    "partner_id": employee_2.id,
                    "line_ids": [Command.create({"product_id": employee_2_product.id})],
                },
            ]
        )
        sale_orders.action_confirm()

        products = company_product | employee_1_product | employee_2_product
        ticket = self.env["helpdesk.ticket"].create({"name": "Ticket"})

        for partner in partners:
            ticket.partner_id = partner
            self.assertEqual(
                ticket.suitable_product_ids,
                products,
                "Products from all children of the parent company should be visible",
            )

    def test_ensure_has_partner_picking(self):
        product, service = self.env["product.product"].create(
            [
                {"name": "Amazing Product", "type": "consu"},
                {"name": "Amazing Service", "type": "service"},
            ]
        )

        partners = self.env["res.partner"].create(
            [
                {
                    "name": name,
                }
                for name in [
                    "No SO",
                    "SO with service",
                    "Draft SO",
                    "Confirmed SO",
                    "Cancelled SO",
                    "Done SO",
                ]
            ]
        )

        service_sale_order = self.env["sale.order"].create(
            [
                {
                    "partner_id": partners[1].id,
                    "line_ids": [(0, 0, {"product_id": service.id})],
                }
            ]
        )

        _draft_so, confirmed_so, canceled_so, done_so = self.env["sale.order"].create(
            [
                {
                    "partner_id": partner.id,
                    "line_ids": [(0, 0, {"product_id": product.id})],
                }
                for partner in partners[2:]
            ]
        )

        (confirmed_so | canceled_so | done_so | service_sale_order).action_confirm()

        canceled_so.with_context(disable_cancel_warning=True).action_cancel()
        self.assertEqual(canceled_so.state, "cancel")

        done_so.picking_ids.move_ids.quantity = 1
        done_so.picking_ids.button_validate()
        self.assertEqual(done_so.picking_ids.state, "done")

        tickets = self.env["helpdesk.ticket"].create(
            [
                {
                    "name": "Amazing ticket",
                    "partner_id": partner.id,
                }
                for partner in partners
            ]
        )

        done_so_ticket = tickets.filtered(lambda t: t.partner_id == done_so.partner_id)
        other_tickets = tickets - done_so_ticket

        self.assertTrue(done_so_ticket.has_partner_picking)
        self.assertEqual(other_tickets.mapped("has_partner_picking"), [False] * 5)

    def test_set_picking_to_false_in_wizard(self):
        product = self.env["product.product"].create(
            {
                "name": "test product",
                "is_storable": True,
                "invoice_policy": "ordered",
            }
        )
        partner = self.env["res.partner"].create({"name": "Customer"})
        so = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
            }
        )
        self.env["sale.order.line"].create(
            {
                "product_id": product.id,
                "price_unit": 10,
                "product_qty": 5,
                "order_id": so.id,
            }
        )
        so.action_confirm()
        delivery_order = so.picking_ids[0]
        delivery_order.move_ids[0].quantity = 5
        delivery_order.button_validate()

        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "test",
                "partner_id": partner.id,
                "team_id": self.test_team.id,
                "sale_order_id": so.id,
            }
        )

        wizard_form = Form(
            self.env["wizard.stock.picking.return"].with_context(
                {"active_model": "helpdesk.ticket", "default_ticket_id": ticket.id}
            )
        )
        wizard_form.picking_id = self.env["stock.picking"]

    def test_return_product_no_sale_order(self):
        product = self.env["product.product"].create(
            {
                "name": "test product",
                "is_storable": True,
                "invoice_policy": "ordered",
            }
        )
        partner = self.env["res.partner"].create({"name": "Customer"})

        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "test",
                "partner_id": partner.id,
                "team_id": self.test_team.id,
            }
        )

        wizard = self.env["wizard.stock.picking.return"].create(
            {"ticket_id": ticket.id, "partner_id": partner.id}
        )

        line = self.env["wizard.stock.picking.return.line"].create(
            {
                "product_id": product.id,
                "quantity": 5,
                "uom_id": product.uom_id.id,
                "wizard_id": wizard.id,
            }
        )

        res = wizard.action_create_returns()
        self.assertTrue(res)
        self.assertEqual(
            line.ids,
            wizard.product_return_moves.ids,
            "the line ids should match the wizard product return moves",
        )

        res_picking = self.env["stock.picking"].search([("id", "=", res.get("res_id"))])
        self.assertEqual(
            res_picking.product_id.id,
            product.id,
            "the product id should match the product selected in the wizard",
        )
        self.assertEqual(
            res_picking.picking_type_code,
            "incoming",
            "the picking type code should be incoming in the return",
        )
        self.assertEqual(
            res_picking.return_id.id,
            wizard.picking_id.id,
            "the return id should match the wizard picking id",
        )

    def test_return_picking_default_multistep_delivery(self):

        warehouse = self.env["stock.warehouse"].create(
            {
                "name": "Multi-Step Test WH",
                "code": "MSWH",
            }
        )
        product_multi_step = self.env["product.product"].create(
            {
                "name": "Multi-Step Test Product",
                "is_storable": True,
            }
        )

        routes = ["pick_ship", "pick_pack_ship"]
        for steps in routes:
            with self.subTest(delivery_steps=steps):
                warehouse.write({"delivery_steps": steps})

                so = self.env["sale.order"].create(
                    {
                        "partner_id": self.partner.id,
                        "warehouse_id": warehouse.id,
                        "line_ids": [
                            Command.create(
                                {"product_id": product_multi_step.id, "product_qty": 1}
                            )
                        ],
                    }
                )
                so.action_confirm()

                final_picking = self.env["stock.picking"]
                current_picking = so.picking_ids
                while current_picking:
                    current_picking.move_ids.quantity = 1
                    current_picking.button_validate()
                    final_picking = current_picking
                    current_picking = current_picking.move_ids.move_dest_ids.picking_id

                self.assertEqual(final_picking.state, "done")

                ticket = self.env["helpdesk.ticket"].create(
                    {
                        "name": f"Return for {steps}",
                        "partner_id": self.partner.id,
                        "team_id": self.test_team.id,
                        "sale_order_id": so.id,
                    }
                )
                return_wizard_form = Form(
                    self.env["wizard.stock.picking.return"].with_context(
                        {
                            "active_model": "helpdesk.ticket",
                            "default_ticket_id": ticket.id,
                        }
                    )
                )

                self.assertEqual(
                    return_wizard_form.picking_id,
                    final_picking,
                    f"For {steps} delivery, the final OUT operation should be defaulted.",
                )
