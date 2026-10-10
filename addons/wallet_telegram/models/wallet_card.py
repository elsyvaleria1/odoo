from odoo import models
from odoo.tools import frozendict


class WalletCard(models.Model):
    """Scope Telegram balance reads to the card's holder."""

    _inherit = "wallet.card"
    _access_anchors = frozendict({"partner": "holder_id"})
