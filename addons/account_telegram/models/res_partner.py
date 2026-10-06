from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"
    _access_verbs = {"print_statement": models.Verb(requires="read")}
