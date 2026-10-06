from odoo import models
from odoo.tools import frozendict


class PurchaseTender(models.Model):
    _inherit = "purchase.tender"

    _access_anchors = frozendict(
        {"team": models.Anchor("user_id.purchase_team_ids", usage="purchase")}
    )


class PurchaseTenderLine(models.Model):
    _inherit = "purchase.tender.line"

    _access_anchors = frozendict(
        {"team": models.Anchor("tender_id.user_id.purchase_team_ids", usage="purchase")}
    )
