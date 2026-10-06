from odoo import fields, models


class SocialTwitterAccount(models.Model):
    _name = "social.twitter.account"
    _description = "Social X Account"

    name = fields.Char()
    description = fields.Char()
    twitter_id = fields.Char(string="X ID")
    image = fields.Binary()

    twitter_searched_by_id = fields.Many2one(
        comodel_name="social.account",
        string="Searched by",
    )
