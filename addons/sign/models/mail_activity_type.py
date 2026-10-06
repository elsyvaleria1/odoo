from odoo import fields, models


class MailActivityType(models.Model):
    _inherit = "mail.activity.type"

    category = fields.Selection(
        selection_add=[
            ("sign_request", "Signature"),
        ],
        ondelete={"sign_request": "set default"},
    )
    default_sign_template_id = fields.Many2one(
        comodel_name="sign.template",
        string="Default Signature Template",
    )
