from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    loan_properties_definition = fields.PropertiesDefinition(string="Model Properties")
