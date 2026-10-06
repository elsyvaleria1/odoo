from odoo import fields, models


class WizardSignRequestSendSigner(models.TransientModel):
    _name = "wizard.sign.request.send.signer"
    _description = "Sign send request signer"

    role_id = fields.Many2one(
        comodel_name="sign.item.role",
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Contact",
    )
    mail_sent_order = fields.Integer(
        string="Sign Order",
        default=1,
    )
    sign_send_request_id = fields.Many2one(comodel_name="wizard.sign.request.send")
