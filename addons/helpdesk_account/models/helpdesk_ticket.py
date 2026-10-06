from odoo import fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    invoices_count = fields.Count(
        count_of="invoice_ids",
        string="Credit Notes Count",
    )
    invoice_ids = fields.Many2many(
        comodel_name="account.move",
        string="Credit Notes",
        copy=False,
    )

    def action_view_credit_notes(self):
        self.check_singleton()
        action = {
            "type": "ir.actions.act_window",
            "name": self.env._("Credit Notes"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.invoice_ids.ids)],
            "context": dict(
                self.env.context,
                default_partner_id=self.partner_id.id,
                default_move_type="out_refund",
                create=False,
            ),
        }
        if self.invoices_count == 1:
            action.update({"view_mode": "form", "res_id": self.invoice_ids.id})
        return action
