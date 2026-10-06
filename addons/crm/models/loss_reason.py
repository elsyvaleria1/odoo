from odoo import fields, models


class LossReason(models.Model):
    _inherit = "loss.reason"

    leads_count = fields.Integer(compute="_compute_leads_count")

    def _compute_leads_count(self) -> None:
        lead_data = (
            self.env["crm.lead"]
            .with_context(active_test=False)
            ._read_group(
                [("lost_reason_id", "in", self.ids)],
                ["lost_reason_id"],
                ["__count"],
            )
        )
        mapped_data = {lost_reason.id: count for lost_reason, count in lead_data}
        for reason in self:
            reason.leads_count = mapped_data.get(reason.id, 0)

    def action_lost_leads(self) -> dict:
        return {
            "name": self.env._("Leads"),
            "view_mode": "list,form",
            "domain": [("lost_reason_id", "in", self.ids)],
            "res_model": "crm.lead",
            "type": "ir.actions.act_window",
            "context": {"create": False, "active_test": False},
        }
