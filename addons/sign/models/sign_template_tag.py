from odoo import models


class SignTemplateTag(models.Model):
    _name = "sign.template.tag"
    _description = "Sign Template Tag"
    _inherit = ["mixin.tag"]
