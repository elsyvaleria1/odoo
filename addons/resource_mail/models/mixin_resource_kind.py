from odoo import models


class MixinResourceKind(models.AbstractModel):
    _name = "mixin.resource.kind"
    _inherit = ["mixin.resource.kind", "mixin.mail.thread", "mixin.mail.activity"]
