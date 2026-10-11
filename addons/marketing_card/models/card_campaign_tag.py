from odoo import models


class CardCampaignTag(models.Model):
    _name = "card.campaign.tag"
    _description = "Marketing Card Campaign Tag"
    _inherit = ["mixin.tag"]
