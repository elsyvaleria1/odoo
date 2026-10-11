from odoo import fields, models


class SocialStreamPostImage(models.Model):

    _name = "social.stream.post.image"
    _description = "Social Stream Post Image Attachment"

    image_url = fields.Char(
        string="Image URL",
        readonly=True,
        required=True,
    )
    stream_post_id = fields.Many2one(
        comodel_name="social.stream.post",
        index="btree_not_null",
        ondelete="cascade",
    )
