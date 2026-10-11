from typing import Any

from odoo import api, models

OPEN_REVIEW_STATES = ("draft", "in_progress")


class HomeTile(models.AbstractModel):
    _inherit = "home.tile"

    _REVIEWS_SHOWN = 5

    @api.model
    def _get_tile_types(self) -> dict[str, dict[str, Any]]:
        return {
            **super()._get_tile_types(),
            "credit_reviews": {
                "name": self.env._("Credit reviews"),
                "sizes": ["1x1", "2x1"],
                "model": "credit.review",
            },
        }

    @api.model
    def _get_tile_credit_reviews_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        Review = self.env["credit.review"]
        domain = [("state", "in", OPEN_REVIEW_STATES), ("user_id", "=", self.env.uid)]
        kinds = dict(Review._fields["kind"]._description_selection(self.env))
        reviews = Review.search(
            domain, limit=self._REVIEWS_SHOWN, order="create_date, id"
        )
        return {
            "count": Review.search_count(domain),
            "reviews": [
                {
                    "id": review.id,
                    "name": review.name,
                    "partner": review.partner_id.display_name,
                    "kind": kinds.get(review.kind, ""),
                }
                for review in reviews
            ],
        }
