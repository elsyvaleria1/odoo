import random

from odoo import models


class UtmCampaign(models.Model):
    _inherit = "utm.campaign"

    def _compute_click_count(self) -> None:
        """Bypass the computation for our demo campaign."""
        demo_campaign = (
            self.env.ref("social_demo.social_utm_campaign", raise_if_not_found=False)
            or self.env["utm.campaign"]
        )
        for campaign in self:
            if campaign == demo_campaign:
                campaign.click_count = random.randint(30000, 40000)

        super(UtmCampaign, self - demo_campaign)._compute_click_count()
