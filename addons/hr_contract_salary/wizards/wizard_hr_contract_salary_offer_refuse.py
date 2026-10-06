from odoo import fields, models
from odoo.exceptions import UserError


class WizardHrContractSalaryOfferRefuse(models.TransientModel):
    _name = "wizard.hr.contract.salary.offer.refuse"
    _description = "Refuse an Offer"

    refusal_reason = fields.Many2one(
        comodel_name="hr.contract.salary.offer.refusal.reason",
        required=True,
    )

    def action_refuse(self):
        offer_ids = self.env["hr.contract.salary.offer"].browse(
            self.env.context.get("active_ids")
        )
        if not offer_ids:
            raise UserError(self.env._("No offer selected"))
        offer_ids.action_refuse_offer(refusal_reason=self.refusal_reason.id)
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "hr_contract_salary.hr_contract_salary_offer_action"
        )
        if len(offer_ids) == 1:
            action["view_mode"] = "form"
            action["res_id"] = offer_ids.id
            action["views"] = [[False, "form"]]
        else:
            action["domain"] = [("id", "in", offer_ids.ids)]
        return action
