from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if "origin" in fields and (
            ticket_id := self.env.context.get("create_for_ticket_id")
        ):
            ticket = self.env["helpdesk.ticket"].browse(ticket_id)
            res["origin"] = self.env._(
                "[Helpdesk] %(ticket_name)s", ticket_name=ticket.name
            )
        return res

    ticket_count = fields.Integer(compute="_compute_ticket_count")

    def _compute_ticket_count(self) -> None:
        if not self.env.user.has_group("helpdesk.group_helpdesk_user"):
            self.ticket_count = 0
            return

        ticket_data = self.env["helpdesk.ticket"]._read_group(
            [
                "|",
                ("sale_order_id", "in", self.ids),
                ("sale_line_id", "in", self.line_ids.ids),
                ("use_helpdesk_sale_timesheet", "=", True),
            ],
            ["sale_order_id"],
            ["__count"],
        )
        mapped_data = {sale_order.id: count for sale_order, count in ticket_data}
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "sale_order_ticket_count",
                orders=self,
                matched_groups=len(mapped_data),
                tickets=sum(mapped_data.values()),
            )
        for so in self:
            so.ticket_count = mapped_data.get(so.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        created_records = super().create(vals_list)
        ticket = self.env["helpdesk.ticket"].browse(
            self.env.context.get("create_for_ticket_id")
        )
        if ticket:
            service_sol = next(
                (sol for sol in created_records.line_ids if sol.is_service), False
            )
            _debug.logic(
                "sale_order_created_for_ticket",
                ticket=ticket,
                orders=created_records,
                service_line=service_sol,
                from_embedded_action=self.env.context.get("from_embedded_action"),
                ticket_already_has_a_line=bool(ticket.sale_line_id),
            )
            if not service_sol and not self.env.context.get("from_embedded_action"):
                raise UserError(
                    self.env._(
                        "The Sales Order must contain at least one service product."
                    )
                )
            if ticket and not ticket.sale_line_id:
                created_records.with_context(
                    disable_project_task_generation=True
                ).action_confirm()
                ticket.sale_line_id = service_sol
        return created_records

    def action_view_tickets(self):
        self.check_singleton()
        sorted_line = self.line_ids.sorted("sequence")
        default_sale_line = next(
            (sol for sol in sorted_line if sol.product_id.type == "service"),
            self.env["sale.order.line"],
        )
        if self.ticket_count > 1:
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "helpdesk.helpdesk_ticket_action_main_tree"
            )
            action.update(
                {
                    "domain": [
                        "|",
                        ("sale_order_id", "=", self.id),
                        ("sale_line_id", "in", self.line_ids.ids),
                    ],
                    "context": self._get_ticket_action_context(default_sale_line),
                }
            )
            return action
        else:
            ticket = self.env["helpdesk.ticket"].search(
                [
                    "|",
                    ("sale_order_id", "=", self.id),
                    ("sale_line_id", "in", self.line_ids.ids),
                ],
                limit=1,
            )
            return {
                "type": "ir.actions.act_window",
                "name": self.env._("Ticket"),
                "res_model": "helpdesk.ticket",
                "views": [
                    (
                        self.env.ref(
                            "helpdesk_sale_timesheet.helpdesk_ticket_view_form_inherit_helpdesk_sale_timesheet"
                        ).id,
                        "form",
                    )
                ],
                "res_id": ticket.id,
                "context": self._get_ticket_action_context(default_sale_line),
            }

    def _get_ticket_action_context(self, default_line) -> dict:
        default_team = self.env["team.team"].search(
            [("use_helpdesk_sale_timesheet", "=", True)], order="sequence", limit=1
        )
        return {
            **self.env.context,
            "default_sale_line_id": default_line.id,
            "default_partner_id": self.partner_id.id,
            "default_sale_order_id": self.id,
            "default_team_id": default_team.id,
            "default_company_id": self.company_id.id,
        }
