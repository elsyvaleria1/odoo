from odoo import fields, models


class UtmTestSourceMixin(models.Model):
    _name = "utm.test.source.mixin"
    _description = "UTM Source Mixin Test Model"
    _order = "id DESC"
    _rec_name = "title"
    _inherit = [
        "mixin.utm.source",
    ]

    name = fields.Char(inherited=True)
    title = fields.Char()


class UtmTestSourceMixinOther(models.Model):
    _name = "utm.test.source.mixin.other"
    _description = "UTM Source Mixin Test Model (another)"
    _order = "id DESC"
    _rec_name = "title"
    _inherit = [
        "mixin.mail.thread",
        "mixin.utm.source",
    ]

    name = fields.Char(inherited=True)
    title = fields.Char()
