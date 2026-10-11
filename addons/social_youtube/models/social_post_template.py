from odoo import models
from odoo.fields import Domain


class SocialPostTemplate(models.Model):
    _inherit = "social.post.template"

    def _get_domain_default_accounts(self):
        youtube_media = self.env.ref("social_youtube.social_media_youtube")
        return Domain.AND(
            [
                super()._get_domain_default_accounts(),
                [("media_id", "!=", youtube_media.id)],
            ]
        )
