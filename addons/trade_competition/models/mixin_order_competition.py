from odoo import api, fields, models

POSITIONS = [
    ("leader", "Leading"),
    ("competitive", "Competitive"),
    ("behind", "Behind the Market"),
    ("cannot_match", "Cannot Match"),
]


class MixinOrderCompetition(models.AbstractModel):
    _name = "mixin.order.competition"
    _description = "Order Measured Against Competitor Offers"

    market_position = fields.Selection(
        selection=POSITIONS,
        compute="_compute_market_position",
        help="The least favourable position among the order's lines.",
    )
    price_gap_at_close = fields.Float(
        string="Gap to Market at Close (%)",
        copy=False,
        readonly=True,
        aggregator="avg",
        help="The order's gap to the market, weighted by line, when it was won "
        "or lost.",
    )

    market_rank = fields.Integer(
        string="Our Rank",
        compute="_compute_market_rank",
        help="Where this order stands among the competitor offers linked to it, "
        "compared on the products each offer quotes: 1 when no offer beats it.",
    )
    market_offer_count = fields.Integer(
        string="Offers Compared",
        compute="_compute_market_rank",
    )

    @api.depends(
        "line_ids.price_unit",
        "line_ids.discount",
        "line_ids.product_qty",
        "competitor_offer_ids.line_ids.price_comparable",
    )
    def _compute_market_rank(self) -> None:
        for order in self:
            offers = order.competitor_offer_ids.filtered(
                lambda offer: offer.active and not offer.is_winner
            )
            order.market_offer_count = len(offers)
            order.market_rank = 1 + sum(
                1 for offer in offers if order._is_beaten_on_basket(offer)
            )

    def _is_beaten_on_basket(self, offer) -> bool:
        self.check_singleton()
        best = self._best_rival_prices(offer)
        ours = theirs = 0.0
        for line in self.line_ids.filtered(
            lambda line: line.product_id in best and not line.display_type
        ):
            qty = line.product_uom_id._get_quantity_in_unit(
                line.product_qty, line.product_id.uom_id, round=False
            )
            ours += self._comparable_net_price(line) * qty
            theirs += best[line.product_id] * qty
        return bool(best) and self._direction.price_sign * (ours - theirs) > 0

    def _best_rival_prices(self, offer):
        sign = self._direction.price_sign
        best = {}
        for line in offer.line_ids.filtered(
            lambda line: line.equivalence in ("same", "comparable")
        ):
            price = best.get(line.product_id)
            if price is None or sign * line.price_comparable < sign * price:
                best[line.product_id] = line.price_comparable
        return best

    def _comparable_net_price(self, line):
        return line._to_comparable(
            line._net_price(), self.company_id, fields.Date.to_date(self.date_order)
        )

    @api.depends("line_ids.market_position")
    def _compute_market_position(self) -> None:
        rank = {key: index for index, (key, _label) in enumerate(POSITIONS)}
        for order in self:
            positions = [p for p in order.line_ids.mapped("market_position") if p]
            order.market_position = max(positions, key=rank.get, default=False)

    def _price_gap_now(self):
        self.check_singleton()
        lines = self.line_ids.filtered("market_position")
        weight = sum(lines.mapped("price_subtotal"))
        if not weight:
            return 0.0
        return sum(line.price_gap * line.price_subtotal for line in lines) / weight

    def _record_price_gap(self) -> None:
        for order in self:
            order.price_gap_at_close = order._price_gap_now()

    def _prepare_confirmation_values(self):
        self._record_price_gap()
        return super()._prepare_confirmation_values()

    def _close_as(self, outcome, loss_reason=None, note=None):
        self._record_price_gap()
        return super()._close_as(outcome, loss_reason=loss_reason, note=note)

    def _beaten_on(self, offer):
        self.check_singleton()
        sign = self._direction.price_sign
        best = self._best_rival_prices(offer)
        return self.line_ids.filtered(
            lambda line: (
                not line.display_type
                and line.product_id in best
                and sign * (self._comparable_net_price(line) - best[line.product_id])
                > 0
            )
        ).product_id

    @api.model
    def _alert_beaten_by(self, offers) -> None:
        orders = self.search(
            [
                ("state", "=", "draft"),
                ("company_id", "in", offers.company_id.ids),
                ("partner_id", "child_of", offers.partner_id.commercial_partner_id.ids),
                ("line_ids.product_id", "in", offers.line_ids.product_id.ids),
            ]
        )
        for offer in offers:
            exposed = orders.filtered(
                lambda order, offer=offer: (
                    order.company_id == offer.company_id
                    and order.partner_id.commercial_partner_id
                    == offer.partner_id.commercial_partner_id
                    and order.line_ids.product_id & offer.line_ids.product_id
                )
            )
            for order in exposed:
                beaten = order._beaten_on(offer)
                if beaten:
                    order.activity_schedule(
                        "mail.mail_activity_data_todo",
                        summary=self.env._("A competitor's offer beats ours"),
                        note=self.env._(
                            "%(competitor)s offers better terms on %(products)s.",
                            competitor=offer.competitor_id.name,
                            products=", ".join(beaten.mapped("display_name")),
                        ),
                        user_id=(order.user_id or self.env.user).id,
                    )

    def action_compare_competitor_offers(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Offers against %(order)s", order=self.name),
            "type": "ir.actions.act_window",
            "res_model": "competitor.offer.line",
            "view_mode": "pivot,list",
            "domain": [("offer_id", "in", self.competitor_offer_ids.ids)],
            "context": {
                "pivot_row_groupby": ["product_id"],
                "pivot_column_groupby": ["competitor_id"],
                "pivot_measures": ["price_comparable"],
            },
        }

    def action_record_competitor_offer(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Competitor Offer"),
            "type": "ir.actions.act_window",
            "res_model": "competitor.offer",
            "view_mode": "form",
            "target": "new",
            "context": {
                f"default_{self._competitor_offer_link}": self.id,
                "default_partner_id": self.partner_id.id,
                "default_direction": self._direction.key,
                "default_currency_id": self.currency_id.id,
                "default_line_ids": [
                    fields.Command.create(
                        {
                            "product_id": line.product_id.id,
                            "product_qty": line.product_qty,
                            "product_uom_id": line.product_uom_id.id,
                        }
                    )
                    for line in self.line_ids
                    if line.product_id and not line.display_type
                ],
            },
        }
