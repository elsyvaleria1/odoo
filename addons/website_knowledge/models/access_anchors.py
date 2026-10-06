from odoo import models
from odoo.tools import frozendict


class KnowledgeArticleFavorite(models.Model):
    _inherit = "knowledge.article.favorite"

    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )


class KnowledgeArticleMember(models.Model):
    _inherit = "knowledge.article.member"

    _access_anchors = frozendict(
        {
            "partner": "partner_id",
        }
    )
