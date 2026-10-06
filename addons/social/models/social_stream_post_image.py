from odoo import fields, models


class SocialStreamPostImage(models.Model):
    """A social.stream.post.image represents an image that was shared with a social.stream.post.
    It only contains the URL of the image on the related social.media."""

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
