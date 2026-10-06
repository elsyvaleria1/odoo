from odoo import models


class MailTemplate(models.Model):
    _name = "mail.template"
    _description = "Email Templates"
    _inherit = ["mixin.studio", "mail.template"]
