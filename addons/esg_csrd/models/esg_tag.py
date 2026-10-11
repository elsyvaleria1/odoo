from odoo import fields, models


class EsgTag(models.Model):
    _name = "esg.tag"
    _description = "ESG Tags"
    _inherit = ["mixin.tag"]

    name = fields.Char(string="Name")
