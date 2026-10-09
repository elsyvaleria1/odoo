from odoo import fields, models


class SignItemRole(models.Model):
    _inherit = "sign.item.role"

    auth_method = fields.Selection(
        selection_add=[("proof", "Code to the Signer's Email or Telegram")],
        ondelete={"proof": "set null"},
    )
