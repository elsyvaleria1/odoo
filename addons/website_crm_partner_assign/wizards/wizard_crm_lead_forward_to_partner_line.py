from odoo import api, fields, models


class WizardCrmLeadForwardToPartnerLine(models.TransientModel):
    _name = "wizard.crm.lead.forward.to.partner.line"
    _description = "Lead Assignation"

    forward_id = fields.Many2one(
        comodel_name="wizard.crm.lead.forward.to.partner",
        string="Partner Assignment",
    )
    lead_id = fields.Many2one(comodel_name="crm.lead")
    lead_location = fields.Char()
    partner_assigned_id = fields.Many2one(
        comodel_name="res.partner",
        string="Assigned Partner",
    )
    partner_location = fields.Char()
    lead_link = fields.Char(string="Link to Lead")

    @api.onchange("lead_id")
    def _onchange_lead_id(self) -> None:
        lead = self.lead_id
        if not lead:
            self.lead_location = False
        else:
            lead_location = []
            if lead.country_id:
                lead_location.append(lead.country_id.name)
            if lead.city:
                lead_location.append(lead.city)
            self.lead_location = ", ".join(lead_location)

    @api.onchange("partner_assigned_id")
    def _onchange_partner_assigned_id(self) -> None:
        partner = self.partner_assigned_id
        if not partner:
            self.lead_location = False
        else:
            partner_location = []
            if partner.country_id:
                partner_location.append(partner.country_id.name)
            if partner.city:
                partner_location.append(partner.city)
            self.partner_location = ", ".join(partner_location)
