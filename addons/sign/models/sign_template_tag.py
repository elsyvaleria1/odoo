from odoo import models


class SignTemplateTag(models.Model):
    _name = "sign.template.tag"
    _description = "Sign Template Tag"
    # `name` (translated, unique on the source term), `active`, `color` and
    # `code` come from the mixin, which already carried the uniqueness rule this
    # model was importing on its own. Flat: template tags do not nest.
    _inherit = ["mixin.tag"]
