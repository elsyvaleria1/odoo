from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools.misc import unquote

from odoo.addons.sale_timesheet_enterprise.models.sale_order_line import (
    DEFAULT_INVOICED_TIMESHEET,
)

_debug = DebugLog(__name__)


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    def _domain_sale_line_id(self):
        return Domain.AND(
            [
                self.env["sale.order.line"]._get_domain_lines_sellable(),
                self.env["sale.order.line"]._domain_sale_line_service(),
                [
                    ("company_id", "=", unquote("company_id")),
                    ("partner_id", "child_of", unquote("commercial_partner_id")),
                ],
            ]
        )

    use_helpdesk_sale_timesheet = fields.Boolean(
        related="team_id.use_helpdesk_sale_timesheet",
        string="Reinvoicing Timesheet activated on Team",
        readonly=True,
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        compute="_compute_helpdesk_sale_order",
        compute_sudo=True,
        store=True,
        readonly=False,
    )
    invoice_count = fields.Integer(
        related="sale_order_id.invoice_count",
        export_string_translation=False,
    )
    display_invoice_button = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_invoice_button",
        compute_sudo=True,
    )
    sale_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sales Order Item",
        compute="_compute_sale_line_id",
        store=True,
        readonly=False,
        domain=lambda self: str(self._domain_sale_line_id()),
        tracking=True,
        help="Sales Order Item to which the time spent on this ticket will be added in order to be invoiced to your customer.\n"
        "By default the last prepaid sales order item that has time remaining will be selected.\n"
        "Remove the sales order item in order to make this ticket non-billable.\n"
        "You can also change or remove the sales order item of each timesheet entry individually.",
    )
    remaining_hours_available = fields.Boolean(
        related="sale_line_id.remaining_hours_available",
        export_string_translation=False,
    )
    remaining_hours_so = fields.Float(
        string="Time Remaining on SO",
        compute="_compute_remaining_hours_so",
        search="_search_remaining_hours_so",
        aggregator="avg",
    )

    @api.constrains("sale_line_id")
    def _check_sale_line_type(self) -> None:
        for ticket in self:
            if ticket.sale_line_id and not ticket.sale_line_id.is_service:
                raise ValidationError(
                    self.env._(
                        "You cannot link order item %(order_id)s - %(product_id)s to this ticket because it is not a service product.",
                        order_id=ticket.sale_line_id.order_id.name,
                        product_id=ticket.sale_line_id.product_id.display_name,
                    )
                )

    @api.depends("sale_line_id", "timesheet_ids", "timesheet_ids.unit_amount")
    def _compute_remaining_hours_so(self) -> None:
        # TODO This is not yet perfectly working as timesheet.so_line stick to its old value although changed
        #      in the task From View.
        timesheets = self.timesheet_ids.filtered(
            lambda t: (
                t.helpdesk_ticket_id.sale_line_id in (t.so_line, t._origin.so_line)
                and t.so_line.remaining_hours_available
            )
        )

        mapped_remaining_hours = {
            ticket._origin.id: (
                ticket.sale_line_id and ticket.sale_line_id.remaining_hours
            )
            or 0.0
            for ticket in self
        }
        uom_hour = self.env.ref("base.product_uom_hour")
        for timesheet in timesheets:
            delta = 0
            if timesheet._origin.so_line == timesheet.helpdesk_ticket_id.sale_line_id:
                delta += timesheet._origin.unit_amount
            if timesheet.so_line == timesheet.helpdesk_ticket_id.sale_line_id:
                delta -= timesheet.unit_amount
            if delta:
                mapped_remaining_hours[timesheet.helpdesk_ticket_id._origin.id] += (
                    timesheet.product_uom_id._get_quantity_in_unit(delta, uom_hour)
                )

        _debug.pipeline(
            "ticket_remaining_hours_so",
            tickets=self,
            # the method carries a TODO saying it is not yet right: a
            # timesheet's `so_line` keeps its old value when changed from the
            # ticket form, which is what the `_origin` pairs below work around
            adjusting_timesheets=timesheets,
        )
        for ticket in self:
            ticket.remaining_hours_so = mapped_remaining_hours[ticket._origin.id]

    @api.model
    def _search_remaining_hours_so(self, operator, value) -> list:
        return [("sale_line_id.remaining_hours", operator, value)]

    @api.depends(
        "partner_id",
        "use_helpdesk_sale_timesheet",
        "project_id.pricing_type",
        "project_id.sale_line_id",
    )
    def _compute_sale_line_id(self) -> None:
        billable_tickets = self.filtered("use_helpdesk_sale_timesheet")
        (self - billable_tickets).update({"sale_line_id": False})
        sol_per_domain = {}
        _debug.pipeline(
            "ticket_sale_line_compute",
            tickets=self,
            billable=billable_tickets,
            cleared=self - billable_tickets,
        )
        for ticket in billable_tickets:
            if ticket.project_id and ticket.project_id.pricing_type != "task_rate":
                ticket.sale_line_id = ticket.project_id.sale_line_id
            # Check sale_line_id and customer are coherent
            if (
                ticket.sale_line_id.sudo().partner_id.commercial_partner_id
                != ticket.commercial_partner_id
            ):
                _debug.logic(
                    "ticket_sale_line_dropped_for_partner_mismatch",
                    ticket=ticket,
                    # the project may have just supplied this line two lines
                    # above, so a project-wide SOL is silently discarded for
                    # any ticket whose customer differs from the order's
                    sale_line=ticket.sale_line_id,
                    ticket_partner=ticket.commercial_partner_id,
                )
                ticket.sale_line_id = False
            if not ticket.sale_line_id:
                domain = Domain(ticket._get_domain_last_sol_of_customer()).optimize(
                    self.env["sale.order.line"]
                )
                if domain.is_true():
                    ticket.sale_line_id = False
                    continue
                domain_str = str(domain)
                if domain_str not in sol_per_domain:
                    sol_per_domain[domain_str] = self.env["sale.order.line"].search(
                        domain, limit=1
                    )
                ticket.sale_line_id = sol_per_domain[domain_str]

    def _compute_display_invoice_button(self) -> None:
        for ticket in self:
            ticket.display_invoice_button = (
                ticket.use_helpdesk_sale_timesheet
                and (ticket.sale_order_id or ticket.sale_line_id)
                and ticket.invoice_count > 0
            )

    def _get_domain_last_sol_of_customer(self):
        # Get the domain of the last SOL made for the customer in the current task where we need to compute
        self.check_singleton()
        if (
            not self.commercial_partner_id
            or not self.project_id.allow_billable
            or not self.use_helpdesk_sale_timesheet
        ):
            return Domain.TRUE
        SaleOrderLine = self.env["sale.order.line"]
        domain = Domain.AND(
            [
                SaleOrderLine._domain_sale_line_service(check_state=False),
                [
                    ("company_id", "=", self.company_id.id),
                    ("partner_id", "child_of", self.commercial_partner_id.id),
                    ("state", "=", "done"),
                    ("remaining_hours", ">", 0),
                ],
            ]
        )
        if (
            self.project_id.pricing_type != "task_rate"
            and (order_id := self.project_id.sale_order_id)
            and self.commercial_partner_id
            == self.project_id.partner_id.commercial_partner_id
        ):
            domain &= Domain("order_id", "=", order_id.id)
        return domain

    @api.model_create_multi
    def create(self, vals_list):
        tickets = super().create(vals_list)
        sol_ids = {
            vals["sale_line_id"] for vals in vals_list if vals.get("sale_line_id")
        }
        if sol_ids:
            tickets._confirm_linked_sale_orders(list(sol_ids))
        return tickets

    def _confirm_linked_sale_orders(self, sol_ids) -> None:
        quotations = (
            self.env["sale.order.line"]
            .sudo()
            ._read_group(
                domain=[("state", "=", "draft"), ("id", "in", sol_ids)],
                aggregates=["order_id:recordset"],
            )[0][0]
        )
        _debug.lifecycle(
            "ticket_confirms_quotations",
            tickets=self,
            sale_line_ids=sol_ids,
            # linking a ticket to a DRAFT order line confirms the whole
            # quotation, as a side effect of creating or writing the ticket
            quotations=quotations,
        )
        if quotations:
            quotations.action_confirm()

    def write(self, vals):
        # an empty recordset, not None: the branch that seeds this one is
        # not the branch that unions into it below, so the two can disagree
        recompute_so_lines = self.env["sale.order.line"]
        other_timesheets = None
        if "timesheet_ids" in vals and isinstance(
            vals.get("timesheet_ids"), (tuple, list)
        ):
            # Then, we check if the list contains tuples/lists like "(code=1, timesheet_id, vals)" and we extract timesheet_id if it is an update and 'so_line' in vals
            timesheet_ids = [
                command[1]
                for command in vals.get("timesheet_ids")
                if isinstance(command, (list, tuple))
                and command[0] == 1
                and "so_line" in command[2]
            ]
            if timesheet_ids:
                recompute_so_lines = self.timesheet_ids.filtered(
                    lambda t: t.id in timesheet_ids
                ).mapped("so_line")
            _debug.logic(
                "ticket_write_timesheet_commands",
                ticket=self,
                # `recompute_so_lines` is seeded only when a command is a
                # type-1 update carrying `so_line`, and the `other_timesheets`
                # branch below is NOT nested under that -- so the two disagree
                updated_timesheets=timesheet_ids,
                writes_a_sale_line=bool(vals.get("sale_line_id")),
                is_approver=self.env.user.has_group(
                    "hr_timesheet.group_hr_timesheet_approver"
                ),
            )
            if not self.env.user.has_group(
                "hr_timesheet.group_hr_timesheet_approver"
            ) and vals.get("sale_line_id", None):
                # We need to search the timesheets of other employee to update the so_line
                other_timesheets = (
                    self.env["account.analytic.line"]
                    .sudo()
                    .search(
                        [
                            ("id", "not in", timesheet_ids),
                            ("helpdesk_ticket_id", "=", self.id),
                        ]
                    )
                )

        res = super().write(vals)
        if sol_id := vals.get("sale_line_id"):
            self._confirm_linked_sale_orders([sol_id])
        if other_timesheets:
            # Then we update the so_line if needed
            compute_timesheets = defaultdict(
                list, [(timesheet, timesheet.so_line) for timesheet in other_timesheets]
            )  # key = timesheet and value = so_line of the timesheet before the _compute_so_line
            other_timesheets._compute_so_line()
            if _debug.logic.enabled:
                _debug.logic(
                    "ticket_other_timesheets_so_line_snapshot",
                    ticket=self,
                    timesheets=other_timesheets,
                    # the "before" snapshot is read AFTER super().write(),
                    # which has already recomputed `so_line` from the new sale
                    # line -- so `before` and `after` are the same value and
                    # the union below is unreachable
                    changed=sum(
                        1
                        for timesheet, sol in compute_timesheets.items()
                        if timesheet.so_line != sol
                    ),
                    snapshot=[sol.id for sol in compute_timesheets.values()],
                    now=other_timesheets.mapped("so_line").ids,
                )
            for timesheet, sol in compute_timesheets.items():
                if timesheet.so_line != sol:
                    recompute_so_lines |= sol
        if recompute_so_lines:
            recompute_so_lines._compute_qty_transferred()
        return res

    @api.depends("sale_line_id", "project_id.sale_order_id")
    def _compute_helpdesk_sale_order(self) -> None:
        for ticket in self:
            if ticket.sale_line_id:
                ticket.sale_order_id = ticket.sale_line_id.order_id
            elif ticket.project_id.sale_order_id:
                ticket.sale_order_id = ticket.project_id.sale_order_id
            else:
                ticket.sale_order_id = False
            if ticket.sale_order_id and not ticket.partner_id:
                ticket.partner_id = ticket.sale_order_id.partner_id

    @api.model
    def _sla_reset_trigger(self):
        field_list = super()._sla_reset_trigger()
        field_list.append("sale_line_id")
        return field_list

    def _sla_find_false_domain(self):
        return Domain.AND(
            [
                super()._sla_find_false_domain(),
                [("product_ids", "=", False)],
            ]
        )

    def _sla_find_extra_domain(self):
        self.check_singleton()
        return Domain.OR(
            [
                super()._sla_find_extra_domain(),
                [("product_ids", "in", self.sale_line_id.product_template_id.ids)],
            ]
        )

    def action_view_so(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "name": self.env._("Sales Order"),
            "views": [[False, "form"]],
            "context": {"create": False, "show_sale": True},
            "res_id": self.sale_line_id.order_id.id or self.sale_order_id.id,
        }

    def action_view_invoices(self):
        self.check_singleton()
        invoices = self.sale_order_id.invoice_ids
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "name": self.env._("Invoices"),
            "views": [[False, "form"]]
            if len(invoices) == 1
            else [[False, "list"], [False, "form"]],
            "context": {"create": False},
            "domain": [("id", "in", invoices.ids)],
            "res_id": invoices.id if len(invoices) == 1 else False,
        }

    def _get_portal_ticket_hours_spent(self):
        if not (
            timesheet_tickets := self.filtered("team_id.use_helpdesk_sale_timesheet")
        ):
            return 0.0
        return (
            self.env["account.analytic.line"]
            .sudo()
            ._read_group(
                [
                    ("helpdesk_ticket_id", "in", timesheet_tickets.ids),
                    (
                        "validated",
                        "in",
                        [
                            True,
                            self.env.registry.settings.get(
                                self.env,
                                "sale.invoiced_timesheet",
                                DEFAULT_INVOICED_TIMESHEET,
                            )
                            == "approved",
                        ],
                    ),
                ],
                [],
                ["unit_amount:sum"],
            )[0][0]
            or 0.0
        )
