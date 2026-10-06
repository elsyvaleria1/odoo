from odoo import fields, models


class WizardResPartnerViewFollowupMissingInfo(models.TransientModel):
    _name = "wizard.res.partner.view.followup.missing.info"
    _description = "Followup missing information wizard"

    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Partners",
    )

    def view_partners_action(self) -> dict:
        """Return a list view of the partners with missing information, editable in place."""
        self.check_singleton()
        return {
            "name": self.env._("Missing information"),
            "res_model": "res.partner",
            "view_mode": "list",
            "views": [
                (
                    self.env.ref("account_followup.missing_information_view_tree").id,
                    "list",
                )
            ],
            "domain": [("id", "in", self.partner_ids.ids)],
            "type": "ir.actions.act_window",
        }
