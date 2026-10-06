from odoo import models
from odoo.tools import frozendict


class SaleTender(models.Model):
    _inherit = "sale.tender"

    _access_anchors = frozendict(
        {"team": models.Anchor("user_id.sale_team_ids", usage="sale")}
    )


class SaleTenderLine(models.Model):
    _inherit = "sale.tender.line"

    _access_anchors = frozendict(
        {"team": models.Anchor("tender_id.user_id.sale_team_ids", usage="sale")}
    )
