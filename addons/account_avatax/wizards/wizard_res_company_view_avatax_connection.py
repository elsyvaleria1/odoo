from odoo import fields, models


class WizardResCompanyViewAvataxConnection(models.TransientModel):
    _name = "wizard.res.company.view.avatax.connection"
    _description = "Test connection with avatax"

    server_response = fields.Html()
