from odoo.exceptions import ValidationError
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.sale_timesheet.tests.common import TestCommonSaleTimesheet


@tagged("-at_install", "post_install", "helpdesk_sale_timesheet")
class TestSaleTimesheetInTicket(TestCommonSaleTimesheet):
    @classmethod
    def get_default_groups(cls):
        return super().get_default_groups() + cls.env.ref(
            "helpdesk.group_helpdesk_manager"
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.helpdesk_team = cls.env["team.team"].create(
            {
                "use_helpdesk": True,
                "name": "Test Team",
                "use_helpdesk_timesheet": True,
                "use_helpdesk_sale_timesheet": True,
                "project_id": cls.project_task_rate.id,
            }
        )

    def test_compute_sale_line_id_in_ticket(self):
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Test Ticket",
                "team_id": self.helpdesk_team.id,
                "partner_id": self.partner_b.id,
            }
        )

        self.assertEqual(
            ticket.sale_line_id,
            self.so.line_ids[-1],
            "The SOL in the ticket should be the one containing the prepaid service product.",
        )

    def test_compute_so_line_in_timesheet(self):
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Test Ticket",
                "team_id": self.helpdesk_team.id,
                "partner_id": self.partner_b.id,
            }
        )

        self.assertEqual(
            ticket.sale_line_id,
            self.so.line_ids[-1],
            "The SOL in the ticket should be the one containing the prepaid service product.",
        )

        timesheet = self.env["account.analytic.line"].create(
            {
                "name": "Test Timesheet",
                "project_id": self.project_task_rate,
                "helpdesk_ticket_id": ticket.id,
                "unit_amount": 2,
                "employee_id": self.employee_user.id,
            }
        )
        self.assertEqual(
            timesheet.so_line,
            ticket.sale_line_id,
            "The SOL in the timesheet should be the one in the ticket.",
        )

        ticket.write({"sale_line_id": self.so.line_ids[0].id})
        self.assertEqual(
            ticket.sale_line_id,
            self.so.line_ids[0],
            "The SOL in the ticket should be the one chosen.",
        )
        self.assertEqual(
            timesheet.so_line,
            ticket.sale_line_id,
            "The SOL in the timesheet should be the one in the ticket.",
        )

    def test_change_customer_and_SOL_after_invoiced_timesheet(self):
        helpdesk_ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Test Ticket",
                "team_id": self.helpdesk_team.id,
                "partner_id": self.partner_b.id,
            }
        )
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_b.id,
                "partner_invoice_id": self.partner_b.id,
                "partner_shipping_id": self.partner_b.id,
            }
        )
        so_line_order_no_task = self.env["sale.order.line"].create(
            {
                "name": self.product_delivery_timesheet1.name,
                "product_id": self.product_delivery_timesheet1.id,
                "product_qty": 1,
                "price_unit": self.product_delivery_timesheet1.list_price,
                "order_id": sale_order.id,
            }
        )

        sale_order.action_confirm()

        timesheet_entry = self.env["account.analytic.line"].create(
            {
                "name": "the only timesheet. So lonely...",
                "helpdesk_ticket_id": helpdesk_ticket.id,
                "project_id": self.helpdesk_team.project_id.id,
                "unit_amount": 3,
                "employee_id": self.employee_user.id,
            }
        )
        helpdesk_ticket.write(
            {
                "sale_line_id": so_line_order_no_task.id,
            }
        )

        self.assertEqual(
            timesheet_entry.partner_id,
            self.partner_b,
            "The Timesheet entry's partner should be equal to the ticket's partner/customer",
        )

        invoice = sale_order._create_invoices()
        invoice.action_post()

        timesheet_entry_2 = self.env["account.analytic.line"].create(
            {
                "name": "A brother for the lonely timesheet",
                "helpdesk_ticket_id": helpdesk_ticket.id,
                "project_id": self.helpdesk_team.project_id.id,
                "unit_amount": 2,
                "employee_id": self.employee_user.id,
            }
        )

        helpdesk_ticket.write({"partner_id": self.partner_a.id})

        self.assertEqual(
            timesheet_entry.partner_id,
            self.partner_b,
            "The invoiced and posted Timesheet entry should have its partner unchanged",
        )
        self.assertEqual(
            timesheet_entry_2.partner_id,
            self.partner_a,
            "The second Timesheet entry should have its partner changed, as it was not invoiced and posted",
        )

    def test_add_timesheet_line_and_get_remaining_so_hours(self):

        uom = self.env["uom.uom"].create(
            {
                "name": "50(hours)",
                "relative_factor": 6.25,
                "relative_uom_id": self.env.ref("base.product_uom_day").id,
            }
        )

        service = self.env["product.product"].create(
            {
                "name": "testService",
                "type": "service",
                "service_policy": "ordered_prepaid",
                "list_price": 1000.0,
                "service_tracking": "task_in_project",
                "uom_id": uom.id,
            }
        )

        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "partner_invoice_id": self.partner_a.id,
                "partner_shipping_id": self.partner_a.id,
            }
        )

        self.env["sale.order.line"].create(
            {
                "name": service.name,
                "product_id": service.id,
                "product_qty": 1,
                "price_unit": service.list_price,
                "order_id": sale_order.id,
                "tax_ids": False,
            }
        )

        sale_order.action_confirm()

        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "test_ticket",
                "sale_order_id": sale_order.id,
                "partner_id": self.partner_a.id,
                "team_id": self.helpdesk_team.id,
            }
        )

        with Form(ticket) as f:
            with f.timesheet_ids.new() as line:
                line.employee_id = self.employee_user
                line.name = ("/",)
                line.unit_amount = 3
            self.assertEqual(f.remaining_hours_so, 47)

    def test_sale_order_helpdesk_team_in_context(self):
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_a.id,
                "partner_invoice_id": self.partner_a.id,
                "partner_shipping_id": self.partner_a.id,
            }
        )
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "test_ticket",
                "sale_order_id": sale_order.id,
                "partner_id": self.partner_a.id,
                "team_id": self.helpdesk_team.id,
            }
        )
        action = sale_order.action_view_tickets()
        self.assertEqual(action["context"]["default_team_id"], ticket.team_id.id)

    def test_compute_commercial_partner_id(self):
        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Test Ticket",
                "team_id": self.helpdesk_team.id,
                "partner_id": self.partner_a.id,
            }
        )
        timesheet = self.env["account.analytic.line"].create(
            {
                "name": "Test Timesheet",
                "project_id": self.helpdesk_team.project_id.id,
                "helpdesk_ticket_id": ticket.id,
                "employee_id": self.employee_user.id,
            }
        )
        self.assertEqual(timesheet.commercial_partner_id, ticket.commercial_partner_id)

    def test_compute_display_sol(self):
        project = self.env["project.project"].create(
            {
                "name": "Test Project",
                "privacy_visibility": "followers",
            }
        )
        timesheet = self.env["account.analytic.line"].create(
            {
                "name": "Test Timesheet",
                "project_id": project.id,
                "employee_id": self.employee_user.id,
            }
        )
        timesheet_manager_no_project_user = new_test_user(
            self.env,
            login="no_project_user",
            groups="hr_timesheet.group_timesheet_manager",
        )
        self.assertFalse(
            timesheet.with_user(timesheet_manager_no_project_user).display_sol,
            "display_sol should be False",
        )

    def test_allowing_service_product_type_sol_in_helpdesk(self):

        sale_order = (
            self.env["sale.order"]
            .with_context(mail_notrack=True, mail_create_nolog=True)
            .create(
                {
                    "partner_id": self.partner_a.id,
                }
            )
        )

        sale_order_line = self.env["sale.order.line"].create(
            {
                "order_id": sale_order.id,
                "product_id": self.product_consumable.id,
                "product_qty": 10,
            }
        )

        sale_order.action_confirm()

        with self.assertRaises(
            ValidationError,
            msg="Creating a helpdesk ticket with a non-service product should raise a ValidationError",
        ):
            self.env["helpdesk.ticket"].create(
                {
                    "name": "Test Ticket with non_service Product",
                    "team_id": self.helpdesk_team.id,
                    "partner_id": self.partner_a.id,
                    "sale_line_id": sale_order_line.id,
                }
            )

    def test_confirm_so_on_ticket_creation(self):
        so1, so2 = self.env["sale.order"].create(
            [
                {
                    "name": "Sale Order 1",
                    "partner_id": self.partner_a.id,
                },
                {
                    "name": "Sale Order 2",
                    "partner_id": self.partner_a.id,
                },
            ]
        )
        sol1, sol2 = self.env["sale.order.line"].create(
            [
                {
                    "order_id": so1.id,
                    "product_id": self.product_delivery_timesheet1.id,
                },
                {
                    "order_id": so2.id,
                    "product_id": self.product_delivery_timesheet1.id,
                },
            ]
        )
        self.assertEqual(so1.state, "draft")
        self.assertEqual(so2.state, "draft")

        self.env["helpdesk.ticket"].create(
            [
                {
                    "name": "Test Ticket 1",
                    "team_id": self.helpdesk_team.id,
                    "sale_line_id": sol1.id,
                },
                {
                    "name": "Test Ticket 2",
                    "team_id": self.helpdesk_team.id,
                    "sale_line_id": sol2.id,
                },
            ]
        )
        self.assertEqual(so1.state, "done")
        self.assertEqual(so2.state, "done")
