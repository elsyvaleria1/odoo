from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import clean_context

from odoo.addons.trade.tools import TradeDirection, direction_of

_debug = DebugLog(__name__)


class MixinTender(models.AbstractModel):
    _name = "mixin.tender"
    _description = "Tender"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _order = "id desc"
    _direction: TradeDirection | None = None

    name = fields.Char(
        string="Tender",
        default=lambda self: self.env._("New"),
        copy=False,
        readonly=True,
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("open", "Open"),
            ("awarded", "Awarded"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        default="open",
        copy=False,
        required=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        default=lambda self: self.env.user,
        check_company=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    date_deadline = fields.Datetime(
        string="Offers Due",
        tracking=True,
        help="When the offers are due. Past it, the tender waits for its award.",
    )
    description = fields.Html()
    order_ids = fields.One2many(
        comodel_name="mixin.order.tender",
        inverse_name="tender_id",
        string="Offers",
    )
    order_count = fields.Count(
        count_of="order_ids",
        string="Offer Count",
    )
    line_ids = fields.One2many(
        comodel_name="mixin.tender.line",
        inverse_name="tender_id",
        string="Needs",
        copy=True,
        help="What the tender asks for. Invited counterparties' offers start "
        "from these lines.",
    )
    is_overdue = fields.Boolean(compute="_compute_is_overdue")

    def _get_sequence_code(self):
        raise NotImplementedError(f"{self._name} must name its sequence")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", self.env._("New")) == self.env._("New"):
                vals["name"] = self.env["ir.sequence"].with_company(
                    vals.get("company_id") or self.env.company.id
                ).next_by_code(self._get_sequence_code()) or self.env._("New")
        return super().create(vals_list)

    @api.depends("state", "date_deadline")
    def _compute_is_overdue(self) -> None:
        now = fields.Datetime.now()
        for tender in self:
            tender.is_overdue = bool(
                tender.state == "open"
                and tender.date_deadline
                and tender.date_deadline < now
            )

    def _get_offer_lines(self):
        return self.order_ids.filtered(
            lambda order: order.state == "draft"
        ).line_ids.filtered(lambda line: not line.display_type and line.product_qty)

    def _comparable_amount(self, line):
        order = line.order_id
        return order.currency_id._convert(
            line.price_subtotal,
            self.company_id.currency_id,
            self.company_id,
            order.date_order or fields.Date.context_today(self),
            round=False,
        )

    def _offer_date(self, line):
        if "date_commitment" in line._fields:
            return line.date_commitment
        return line.order_id.date_commitment

    def _better(self, value, best) -> bool:
        # we choose the offer: when we buy the lowest price is best, when we
        # sell the highest (price_sign is -1 for a purchase, +1 for a sale)
        sign = direction_of(self).price_sign
        return value * sign > best * sign

    def _get_best_lines(self) -> dict:
        self.check_singleton()
        best_total = defaultdict(lambda: self.env[self.order_ids.line_ids._name])
        best_unit = defaultdict(lambda: self.env[self.order_ids.line_ids._name])
        best_date = defaultdict(lambda: self.env[self.order_ids.line_ids._name])
        total_of, unit_of = {}, {}
        for line in self._get_offer_lines():
            total = self._comparable_amount(line)
            unit = total / line.product_qty
            total_of[line], unit_of[line] = total, unit
            product = line.product_id
            for best, value_of in ((best_total, total_of), (best_unit, unit_of)):
                current = best[product]
                if not current or self._better(value_of[line], value_of[current[0]]):
                    best[product] = line
                elif value_of[line] == value_of[current[0]]:
                    best[product] |= line
            current = best_date[product]
            date = self._offer_date(line)
            current_date = current and self._offer_date(current[0])
            if not current or (date and (not current_date or date < current_date)):
                best_date[product] = line
            elif date == current_date:
                best_date[product] |= line
        return {
            "best_total": [line.id for lines in best_total.values() for line in lines],
            "best_unit": [line.id for lines in best_unit.values() for line in lines],
            "best_date": [line.id for lines in best_date.values() for line in lines],
        }

    def action_award(self) -> None:
        self.check_singleton()
        if self.state != "open":
            raise UserError(self.env._("Only an open tender can be awarded."))
        offers = self.order_ids.filtered(lambda order: order.state == "draft")
        awarded_lines = offers.line_ids.filtered(
            lambda line: not line.display_type and line.qty_awarded > 0
        )
        if not awarded_lines:
            raise UserError(
                self.env._(
                    "Award at least one line before awarding the tender: choose it in "
                    "the comparison, or set its awarded quantity."
                )
            )
        winners = awarded_lines.order_id
        self._award_to(winners, awarded_lines)
        losers = offers - winners
        if losers:
            losers._close_as(
                "rejected",
                note=self.env._("Not awarded in %(tender)s.", tender=self.name),
            )
        self.state = "awarded"
        _debug.lifecycle("tender_awarded", tender=self, winners=winners, losers=losers)

    def _award_to(self, winners, awarded_lines):
        for order in winners:
            product_lines = order.line_ids.filtered(lambda line: not line.display_type)
            (product_lines - awarded_lines).unlink()
            for line in order.line_ids & awarded_lines:
                if line.product_qty != line.qty_awarded:
                    line.product_qty = line.qty_awarded
        winners.with_context(skip_tender_check=True).action_confirm()

    def action_cancel(self):
        for tender in self:
            open_offers = tender.order_ids.filtered(
                lambda order: order.state == "draft"
            )
            if open_offers:
                open_offers.action_cancel()
        self.state = "cancel"

    def action_invite(self):
        self.check_singleton()
        return {
            "name": self.env._("Invite to %(tender)s", tender=self.name),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": self.env[
                self._fields["order_ids"].comodel_name
            ]._tender_invite_model,
            "target": "new",
            "context": {"default_tender_id": self.id},
        }

    def action_reopen(self) -> None:
        self.filtered(lambda tender: tender.state == "cancel").state = "open"


class MixinOrderTender(models.AbstractModel):
    _name = "mixin.order.tender"
    _description = "Order Offered in a Tender"

    _tender_invite_model = ""
    _tender_warning_model = ""

    tender_id = fields.Many2one(
        comodel_name="mixin.tender",
        string="Tender",
        index="btree_not_null",
        copy=False,
        check_company=True,
    )

    def _get_open_rival_offers(self):
        return (self.tender_id.order_ids - self).filtered(
            lambda order: order.state == "draft"
        )

    def action_confirm(self):
        if not self.env.context.get("skip_tender_check"):
            rivals = self._get_open_rival_offers()
            if rivals:
                return {
                    "name": self.env._("What about the other offers of the tender?"),
                    "type": "ir.actions.act_window",
                    "view_mode": "form",
                    "res_model": self._tender_warning_model,
                    "target": "new",
                    "context": dict(
                        self.env.context,
                        default_rival_ids=rivals.ids,
                        default_order_ids=self.ids,
                    ),
                }
        return super().action_confirm()

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        origin_id = self.env.context.get("tender_origin_id")
        if origin_id:
            self.browse(origin_id)._get_or_create_tender().order_ids |= orders
        return orders

    def _get_or_create_tender(self):
        self.check_singleton()
        if not self.tender_id:
            Tender = self.env[self._fields["tender_id"].comodel_name]
            Need = self.env[Tender._fields["line_ids"].comodel_name]
            self.tender_id = Tender.create(
                {
                    "company_id": self.company_id.id,
                    "user_id": self.user_id.id or self.env.user.id,
                    "line_ids": [
                        fields.Command.create(
                            Need._prepare_values_from_order_line(
                                line, fields.Date.to_date(Tender._offer_date(line))
                            )
                        )
                        for line in self.line_ids
                        if line.product_id and not line.display_type
                    ],
                }
            )
        return self.tender_id

    def action_invite_counterparties(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Invite to the tender"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": self._tender_invite_model,
            "target": "new",
            "context": {
                **clean_context(self.env.context),
                "default_origin_order_id": self.id,
            },
        }


class MixinOrderLineTender(models.AbstractModel):
    _name = "mixin.order.line.tender"
    _description = "Order Line Offered in a Tender"

    is_best_total = fields.Boolean(
        string="Best Total",
        compute="_compute_best_offer",
    )
    is_best_unit = fields.Boolean(
        string="Best Unit Price",
        compute="_compute_best_offer",
    )
    is_best_date = fields.Boolean(
        string="Best Date",
        compute="_compute_best_offer",
    )

    qty_awarded = fields.Float(
        string="Awarded",
        digits="Product Unit",
        copy=False,
        help="The quantity of this offer the tender awards. Awarding the tender "
        "confirms the offers with an award at these quantities and rejects the "
        "others.",
    )

    def _compute_best_offer(self) -> None:
        best_by_tender = {
            tender: tender._get_best_lines() for tender in self.order_id.tender_id
        }
        for line in self:
            best = best_by_tender.get(line.order_id.tender_id)
            line.is_best_total = bool(best) and line.id in best["best_total"]
            line.is_best_unit = bool(best) and line.id in best["best_unit"]
            line.is_best_date = bool(best) and line.id in best["best_date"]

    def action_award_line(self) -> None:
        rivals = self._get_rival_lines()
        rivals.qty_awarded = 0.0
        for line in self:
            line.qty_awarded = line.product_qty

    def action_clear_award(self) -> None:
        self.qty_awarded = 0.0

    def _get_rival_lines(self):
        offers = self.order_id.tender_id.order_ids
        return offers.line_ids.filtered(
            lambda line: (
                line.product_id in self.product_id
                and line not in self
                and line.order_id.state == "draft"
            )
        )
