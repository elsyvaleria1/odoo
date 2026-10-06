from odoo import fields, models


class SocialStreamType(models.Model):
    """Technical model that allows social module implementations ('social_facebook', 'social_twitter', ...)
    to introduce their own social stream types (eg: 'Page Posts' for Facebook, 'Keyword' for Twitter, ...)"""

    _name = "social.stream.type"
    _description = "Social Stream Post"

    name = fields.Char(
        translate=True,
        readonly=True,
        required=True,
    )
    stream_type = fields.Char(
        string="Stream type name (technical)",
        readonly=True,
        required=True,
    )
    media_id = fields.Many2one(
        comodel_name="social.media",
        string="Social Media",
        index=True,
        readonly=True,
        required=True,
    )
