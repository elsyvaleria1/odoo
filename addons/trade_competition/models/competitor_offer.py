from datetime import timedelta

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.trade.tools import PURCHASE, SALE
from odoo.addons.trade_competition.tools import to_comparable

_debug = DebugLog(__name__)

DIRECTIONS = {"sale": SALE, "purchase": PURCHASE}

MARKET_MEMORY_DAYS = 90


class CompetitorOffer(models.Model):
    _name = "competitor.offer"
    _description = "Competitor Offer"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    active = fields.Boolean(default=True)
    competitor_id = fields.Many2one(
        comodel_name="res.partner",
        string="Competitor",
        index=True,
        required=True,
        domain=[("is_competitor", "=", True)],
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Offered To",
        index=True,
        required=True,
        tracking=True,
        help="Our counterparty the competitor made this offer to: a customer when "
        "we sell, a grower or vendor when we buy.",
    )
    direction = fields.Selection(
        selection=[
            ("sale", "Competing to Sell"),
            ("purchase", "Competing to Buy"),
        ],
        default=lambda self: self.env.context.get("default_direction", "sale"),
        index=True,
        required=True,
    )
    date = fields.Date(
        string="Seen On",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    date_valid = fields.Date(
        string="Valid Until",
        help="The last day the offer stands. Without it, the offer is read as the "
        "market for 90 days.",
    )
    source = fields.Selection(
        selection=[
            ("customer_feedback", "Told by the Counterparty"),
            ("public_tender", "Public Tender Result"),
            ("price_list", "Competitor's Price List"),
            ("field_visit", "Field Visit"),
            ("document_seen", "Document Seen"),
            ("other", "Other"),
        ],
        default="customer_feedback",
        required=True,
    )
    confidence = fields.Selection(
        selection=[
            ("confirmed", "Confirmed"),
            ("reported", "Reported"),
            ("estimated", "Estimated"),
        ],
        default="reported",
        required=True,
    )
    is_winner = fields.Boolean(
        string="Won the Deal",
        tracking=True,
        help="This offer won the deal it was made for.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Recorded By",
        default=lambda self: self.env.user,
    )
    payment_term_id = fields.Many2one(
        comodel_name="account.payment.term",
        string="Payment Terms",
    )
    incoterm_id = fields.Many2one(
        comodel_name="account.incoterms",
        string="Incoterm",
        help="Who carries the goods and their risk in the competitor's offer, "
        "which its price includes or leaves to the counterparty.",
    )
    credit_days = fields.Integer(
        compute="_compute_credit_days",
        store=True,
        readonly=False,
        help="Days of credit the offer gives, read from its payment terms.",
    )
    freight_per_unit = fields.Monetary(
        string="Freight per Unit",
        currency_field="currency_id",
        help="Freight the competitor leaves to the counterparty, per unit.",
    )
    note = fields.Html()
    line_ids = fields.One2many(
        comodel_name="competitor.offer.line",
        inverse_name="offer_id",
        string="Lines",
        copy=True,
    )
    amount_total = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
    )

    @api.depends("competitor_id", "partner_id", "date")
    def _compute_name(self):
        for offer in self:
            offer.name = self.env._(
                "%(competitor)s to %(partner)s, %(date)s",
                competitor=offer.competitor_id.name or "?",
                partner=offer.partner_id.name or "?",
                date=offer.date or "",
            )

    @api.depends("payment_term_id.line_ids.nb_days")
    def _compute_credit_days(self) -> None:
        for offer in self:
            offer.credit_days = max(
                offer.payment_term_id.line_ids.mapped("nb_days"), default=0
            )

    @api.depends("line_ids.price_subtotal")
    def _compute_amount_total(self) -> None:
        for offer in self:
            offer.amount_total = sum(offer.line_ids.mapped("price_subtotal"))

    @api.model_create_multi
    def create(self, vals_list):
        offers = super().create(vals_list)
        offers._alert_beaten_orders()
        return offers

    def _competition_order_models(self) -> list:
        return []

    def _alert_beaten_orders(self) -> None:
        for model in self._competition_order_models():
            Order = self.env[model]
            offers = self.filtered(
                lambda offer, key=Order._direction.key: offer.direction == key
            )
            if offers:
                Order._alert_beaten_by(offers)


class CompetitorOfferLine(models.Model):
    _name = "competitor.offer.line"
    _description = "Competitor Offer Line"
    _order = "offer_id, sequence, id"
    _check_company_auto = True

    offer_id = fields.Many2one(
        comodel_name="competitor.offer",
        index=True,
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(related="offer_id.company_id")
    competitor_id = fields.Many2one(related="offer_id.competitor_id")
    partner_id = fields.Many2one(related="offer_id.partner_id")
    direction = fields.Selection(related="offer_id.direction")
    date = fields.Date(related="offer_id.date")
    currency_id = fields.Many2one(related="offer_id.currency_id")
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Our Product",
        index=True,
        required=True,
        check_company=True,
        help="Our product the offered one competes with.",
    )
    product_category_id = fields.Many2one(related="product_id.categ_id")
    competitor_product = fields.Char(
        string="Their Product",
        help="The competitor's brand, variety or grade, when it is not ours.",
    )
    equivalence = fields.Selection(
        selection=[
            ("same", "Same"),
            ("comparable", "Comparable"),
            ("inferior", "Inferior"),
            ("superior", "Superior"),
        ],
        default="same",
        required=True,
        help="How the offered product compares with ours. The market price reads "
        "only same and comparable offers.",
    )
    product_qty = fields.Float(
        string="Quantity",
        digits="Product Unit",
        default=1.0,
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit",
        compute="_compute_product_uom_id",
        precompute=True,
        store=True,
        readonly=False,
    )
    price_unit = fields.Monetary(
        string="Unit Price",
        currency_field="currency_id",
    )
    discount = fields.Float(
        string="Discount (%)",
        digits="Discount",
    )
    price_subtotal = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_price_subtotal",
        store=True,
    )
    price_comparable = fields.Float(
        string="Comparable Price",
        compute="_compute_price_comparable",
        store=True,
        aggregator="avg",
        help="Net of discount, in the company's currency, per the product's "
        "reference unit, and adjusted for freight and credit where the company "
        "asks for it.",
    )

    @api.depends("product_id")
    def _compute_product_uom_id(self):
        for line in self:
            line.product_uom_id = line.product_id.uom_id

    @api.depends("price_unit", "discount", "product_qty")
    def _compute_price_subtotal(self) -> None:
        for line in self:
            line.price_subtotal = (
                line.price_unit * (1 - line.discount / 100) * line.product_qty
            )

    @api.depends(
        "price_unit",
        "discount",
        "product_uom_id",
        "product_id.uom_id",
        "offer_id.currency_id",
        "offer_id.date",
        "offer_id.company_id",
        "offer_id.freight_per_unit",
        "offer_id.credit_days",
        "offer_id.direction",
    )
    def _compute_price_comparable(self) -> None:
        for line in self:
            line.price_comparable = line._comparable(
                line.price_unit * (1 - line.discount / 100)
            )

    def _comparable(self, price):
        self.check_singleton()
        offer = self.offer_id
        company = offer.company_id or self.env.company
        date = offer.date or fields.Date.context_today(self)
        config = company.trade_config_id
        if config.competition_freight_adjusted and offer.freight_per_unit:
            price += DIRECTIONS[offer.direction].price_sign * offer.freight_per_unit
        price = to_comparable(
            price,
            unit=self.product_uom_id,
            product=self.product_id,
            currency=offer.currency_id,
            company=company,
            date=date,
        )
        if config.competition_financing_rate and offer.credit_days:
            price /= 1 + config.competition_financing_rate / 100 * (
                offer.credit_days / 365
            )
        return price

    @api.model
    def _get_market_prices(self, keys, direction, date, company):
        products = self.env["product.product"].union(*(key[0] for key in keys))
        if not products:
            return {}
        lines = self.search(
            [
                ("product_id", "in", products.ids),
                ("direction", "=", direction),
                ("company_id", "in", [company.id, False]),
                ("equivalence", "in", ["same", "comparable"]),
                ("date", "<=", date),
                ("offer_id.active", "=", True),
                "|",
                ("offer_id.date_valid", ">=", date),
                "&",
                ("offer_id.date_valid", "=", False),
                ("date", ">=", date - timedelta(days=MARKET_MEMORY_DAYS)),
            ]
        )
        sign = DIRECTIONS[direction].price_sign
        by_product = lines.grouped("product_id")
        result = {}
        for product, partner in keys:
            candidates = by_product.get(product, self.browse())
            commercial = partner.commercial_partner_id
            own = candidates.filtered(
                lambda line, commercial=commercial: (
                    line.partner_id.commercial_partner_id == commercial
                )
            )
            industry = commercial.primary_industry_id
            peers = (
                candidates.filtered(
                    lambda line, industry=industry: (
                        line.partner_id.commercial_partner_id.primary_industry_id
                        == industry
                    )
                )
                if industry and not own
                else candidates.browse()
            )
            if own:
                scope, pool = "partner", own
            elif peers:
                scope, pool = "segment", peers
            else:
                scope, pool = "market", candidates
            if not pool:
                continue
            best = min(pool, key=lambda line: line.price_comparable * sign)
            result[product, partner] = (best.price_comparable, scope, best)
        _debug.perf.count("market_prices", keys=len(keys), lines=len(lines))
        return result
