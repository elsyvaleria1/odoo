from odoo import api, fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    partner_company_name = fields.Char(
        string="Company Name",
        compute="_compute_partner_company_name",
        store=True,
        readonly=False,
    )

    @api.depends("partner_id.commercial_company_name")
    def _compute_partner_company_name(self) -> None:
        for ticket in self:
            if company_name := ticket.partner_id.commercial_company_name:
                ticket.partner_company_name = company_name
            elif not ticket.partner_company_name:
                ticket.partner_company_name = False
