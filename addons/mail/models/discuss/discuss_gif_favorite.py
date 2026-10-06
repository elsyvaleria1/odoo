from odoo import api, fields, models
from odoo.db import get_or_create_row
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DiscussGifFavorite(models.Model):
    _name = "discuss.gif.favorite"
    _description = "Save favorite GIF from Tenor API"

    tenor_gif_id = fields.Char(
        string="GIF id from Tenor",
        required=True,
    )

    _user_gif_favorite = models.Constraint(
        "unique(create_uid,tenor_gif_id)",
        "User should not have duplicated favorite GIF",
    )

    @api.model
    def _add_favorite(self, tenor_gif_id: str) -> None:
        domain = [
            ("create_uid", "=", self.env.uid),
            ("tenor_gif_id", "=", tenor_gif_id),
        ]
        if self.search_count(domain, limit=1):
            _debug.logic("gif_favorite_present", uid=self.env.uid)
            return
        get_or_create_row(
            self.env.cr,
            lambda: self.create({"tenor_gif_id": tenor_gif_id}),
            lambda: self.search(domain, limit=1),
            conflict="discuss.gif.favorite",
        )
