from odoo import fields, models


class ProofChallenge(models.Model):
    _inherit = "proof.challenge"

    code_hash = fields.Char(
        copy=False,
        readonly=True,
        help="HMAC of the one-time code sent by email, under the database secret.",
    )
    code_attempts = fields.Integer(
        default=0,
        copy=False,
        readonly=True,
    )
    code_sent_to = fields.Char(
        string="Code Sent To",
        copy=False,
        readonly=True,
        help="The address the code went to, masked.",
    )
