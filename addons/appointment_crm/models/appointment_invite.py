from odoo import fields, models


class AppointmentInvite(models.Model):
    _inherit = "appointment.invite"

    opportunity_id = fields.Many2one(
        comodel_name="crm.lead",
        string="Opportunity/Lead",
        help="Link an opportunity/lead to the appointment invite created.\n"
        "Used when creating an invitation from the Meeting action in the crm form view.",
    )
