from odoo import models
from odoo.tools import frozendict


class WalletCard(models.Model):

    _inherit = "wallet.card"
    _access_anchors = frozendict({"partner": "holder_id"})
