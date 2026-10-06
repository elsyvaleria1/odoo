from odoo import fields, models


class EsgTag(models.Model):
    _name = "esg.tag"
    _description = "ESG Tags"
    # `name` (translated, unique on the source term), `active`, `color` and
    # `code` come from the mixin, which already carried the uniqueness rule this
    # model was importing on its own. Flat: ESG tags do not nest.
    _inherit = ["mixin.tag"]

    name = fields.Char(string="Name")
