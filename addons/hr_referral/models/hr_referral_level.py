from odoo import fields, models


class HrReferralLevel(models.Model):
    _name = "hr.referral.level"
    _description = "Level for referrals"
    _order = "points"

    name = fields.Char(
        string="Level Name",
        required=True,
    )
    points = fields.Integer(required=True)
    image = fields.Binary(required=True)
