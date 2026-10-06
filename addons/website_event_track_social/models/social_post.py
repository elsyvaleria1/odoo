from odoo import fields, models


class SocialPost(models.Model):
    _inherit = "social.post"

    event_track_id = fields.Many2one(
        comodel_name="event.track",
        string="Linked Event Track",
        index="btree_not_null",
        ondelete="cascade",
    )
