from odoo import fields, models


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    sale_order_line_ids = fields.One2many(
        comodel_name="sale.order.line",
        inverse_name="calendar_event_id",
    )
    sale_order_count = fields.Integer(
        string="Sales Order Count",
        compute="_compute_sale_order_count",
    )

    def _compute_sale_order_count(self) -> None:
        sol_data = self.env["sale.order.line"]._read_group(
            domain=[("calendar_event_id", "in", self.ids)],
            groupby=["calendar_event_id"],
            aggregates=["order_id:count_distinct"],
        )
        mapped_data = {event.id: count for event, count in sol_data}
        for event in self:
            event.sale_order_count = mapped_data.get(event.id, 0)

    def action_view_sale_order(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "sale.action_sale_order"
        )
        action["context"] = {"active_test": False}
        action["res_id"] = (
            self.sale_order_line_ids[0].order_id.id
            if self.sale_order_line_ids
            else False
        )
        action["views"] = [(False, "form")]
        return action
