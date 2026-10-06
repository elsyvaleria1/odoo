from typing import Any

from odoo import api, models
from odoo.tools import format_amount


class HomeTile(models.AbstractModel):
    _inherit = "home.tile"

    _LOW_CARDS_SHOWN = 6

    @api.model
    def _get_tile_types(self) -> dict[str, dict[str, Any]]:
        return {
            **super()._get_tile_types(),
            "wallet_low": {
                "name": self.env._("Low wallet balances"),
                "sizes": ["1x1", "2x1"],
                "model": "wallet.card",
            },
        }

    @api.model
    def _get_tile_wallet_low_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        Card = self.env["wallet.card"]
        domain = [("is_low_balance", "=", True)]
        cards = Card.search(
            domain, limit=self._LOW_CARDS_SHOWN, order="amount_balance, id"
        )
        return {
            "count": Card.search_count(domain),
            "cards": [
                {
                    "id": card.id,
                    "name": card.display_name,
                    "account": card.account_id.display_name,
                    "balance": format_amount(
                        self.env, card.amount_balance, card.currency_id
                    ),
                    "threshold": format_amount(
                        self.env, card.amount_threshold_low, card.currency_id
                    ),
                }
                for card in cards
            ],
        }
