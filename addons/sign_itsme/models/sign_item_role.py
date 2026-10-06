from odoo import fields, models


class SignItemRole(models.Model):
    _inherit = "sign.item.role"

    auth_method = fields.Selection(
        selection_add=[("itsme", "Via itsme®")],
        ondelete={"itsme": "cascade"},
    )
