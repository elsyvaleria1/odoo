import random

from odoo import models


class SocialPost(models.Model):
    _inherit = "social.post"

    def _compute_click_count(self) -> None:
        """Let's add some random click statistics on our posts to make them look better."""
        for post in self:
            post.click_count = random.randint(10000, 30000)
