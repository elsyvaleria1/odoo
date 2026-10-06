from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    phone_call_count = fields.Integer(
        string="Calls",
        compute="_compute_phone_call_count",
    )

    def _compute_phone_call_count(self) -> None:
        counts = dict(
            self.env["phone.call"]._read_group(
                [("partner_id", "in", self.ids)],
                groupby=["partner_id"],
                aggregates=["__count"],
            )
        )
        for partner in self:
            partner.phone_call_count = counts.get(partner, 0)

    def action_view_phone_calls(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Calls"),
            "res_model": "phone.call",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
        }
