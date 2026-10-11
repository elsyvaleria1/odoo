import random

from odoo import models


class SocialPost(models.Model):
    _inherit = "social.post"

    def _compute_click_count(self) -> None:
        for post in self:
            post.click_count = random.randint(10000, 30000)
