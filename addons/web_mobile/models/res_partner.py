from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Kept under this exact name because the native mobile app's avatar-fetch
    # bridge (web_mobile/static/src/js/core/mixins.js, fetchAvatar()) hardcodes
    # field=image_medium in its request URL. Renaming or removing this field
    # breaks avatar fetching for already-shipped app builds, independent of
    # server version.
    image_medium = fields.Binary(
        related="avatar_128",
        string="Medium-sized image",
        store=False,
        readonly=True,
    )
