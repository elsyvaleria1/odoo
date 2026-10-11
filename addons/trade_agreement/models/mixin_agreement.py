from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog

from odoo.addons.trade.tools import TradeDirection

_debug = DebugLog(__name__)


class MixinAgreement(models.AbstractModel):
    _name = "mixin.agreement"
    _description = "Trade Agreement"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _order = "id desc"
    _direction: TradeDirection | None = None

    name = fields.Char(
        string="Agreement",
        default=lambda self: self.env._("New"),
        copy=False,
        readonly=True,
        required=True,
    )
    active = fields.Boolean(default=True)
    reference = fields.Char()
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        check_company=True,
    )
    agreement_type = fields.Selection(
        selection=[("blanket_order", "Blanket Order")],
        string="Agreement Type",
        default="blanket_order",
        required=True,
    )
    date_start = fields.Date(
        string="Start Date",
        tracking=True,
    )
    date_end = fields.Date(
        string="End Date",
        tracking=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.user,
        check_company=True,
    )
    description = fields.Html()
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("done", "Closed"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        default="draft",
        copy=False,
        required=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_currency_id",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    commitment = fields.Selection(
        selection=[
            ("price", "Prices Only"),
            ("quantity", "Quantity"),
            ("value", "Value"),
        ],
        default="quantity",
        required=True,
        tracking=True,
        help="Prices only: the agreed prices apply, with no volume promised. "
        "Quantity: each line commits its quantity. Value: the agreement commits "
        "a total amount.",
    )
    amount_committed = fields.Monetary(
        string="Committed Amount",
        currency_field="currency_id",
        tracking=True,
    )
    amount_ordered = fields.Monetary(
        string="Ordered Amount",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    amount_remaining = fields.Monetary(
        string="Remaining Amount",
        currency_field="currency_id",
        compute="_compute_amounts",
        store=True,
    )
    consumed_percent = fields.Float(
        string="Consumed",
        compute="_compute_consumed_percent",
        store=True,
        aggregator="max",
        help="For a value commitment, the share of the amount ordered; for a "
        "quantity commitment, the share ordered of its most consumed line.",
    )
    overrelease_policy = fields.Selection(
        selection=[
            ("allow", "Allow"),
            ("warn", "Warn"),
            ("block", "Block"),
        ],
        string="Beyond the Commitment",
        default="warn",
        required=True,
        help="What confirming an order does when it would exceed what remains of "
        "the commitment, or falls outside the agreement's dates.",
    )
    previous_agreement_id = fields.Many2one(
        comodel_name="mixin.agreement",
        string="Renews",
        copy=False,
        readonly=True,
    )
    reminded_expiry = fields.Boolean(copy=False)
    reminded_consumption = fields.Boolean(copy=False)

    def _get_sequence_code(self, agreement_type):
        raise NotImplementedError(
            f"{self._name} must name the sequence of each agreement type"
        )

    def _get_partner_currency(self, partner):
        return self.env["res.currency"]

    @api.depends("partner_id")
    def _compute_currency_id(self) -> None:
        for agreement in self:
            agreement.currency_id = (
                agreement._get_partner_currency(agreement.partner_id)
                or agreement.company_id.currency_id
            )

    @api.depends("commitment", "amount_committed", "line_ids.amount_ordered")
    def _compute_amounts(self) -> None:
        for agreement in self:
            agreement.amount_ordered = sum(agreement.line_ids.mapped("amount_ordered"))
            agreement.amount_remaining = (
                agreement.amount_committed - agreement.amount_ordered
                if agreement.commitment == "value"
                else 0.0
            )

    @api.depends(
        "commitment",
        "amount_committed",
        "amount_ordered",
        "line_ids.product_qty",
        "line_ids.qty_ordered",
    )
    def _compute_consumed_percent(self) -> None:
        for agreement in self:
            if agreement.commitment == "value":
                agreement.consumed_percent = (
                    100.0 * agreement.amount_ordered / agreement.amount_committed
                    if agreement.amount_committed
                    else 0.0
                )
            elif agreement.commitment == "quantity":
                agreement.consumed_percent = max(
                    (
                        100.0 * line.qty_ordered / line.product_qty
                        for line in agreement.line_ids
                        if line.product_qty
                    ),
                    default=0.0,
                )
            else:
                agreement.consumed_percent = 0.0

    @api.onchange("partner_id")
    def _onchange_partner_id_open_blanket_order(self) -> dict | None:
        if not self.partner_id:
            return None
        open_blanket_orders = self.search_count(
            [
                ("partner_id", "child_of", self.partner_id.commercial_partner_id.id),
                ("state", "=", "confirmed"),
                ("agreement_type", "=", "blanket_order"),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        if not open_blanket_orders:
            return None
        return {
            "warning": {
                "title": self.env._("Warning for %s", self.partner_id.name),
                "message": self.env._(
                    "There is already an open blanket order for this partner. We "
                    "suggest you complete this open blanket order, instead of "
                    "creating a new one."
                ),
            }
        }

    @api.constrains("date_start", "date_end")
    def _check_dates(self) -> None:
        invalid = self.filtered(
            lambda agreement: (
                agreement.date_end
                and agreement.date_start
                and agreement.date_end < agreement.date_start
            )
        )
        if invalid:
            raise ValidationError(
                self.env._(
                    "End date cannot be earlier than start date. Please check dates "
                    "for agreements: %s",
                    ", ".join(invalid.mapped("name")),
                )
            )

    def _next_name(self, agreement_type, company_id):
        return (
            self.env["ir.sequence"]
            .with_company(company_id)
            .next_by_code(self._get_sequence_code(agreement_type))
        )

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(["agreement_type", "company_id"])
        for vals in vals_list:
            vals["name"] = self._next_name(
                vals.get("agreement_type", defaults["agreement_type"]),
                vals.get("company_id", defaults["company_id"]),
            )
        return super().create(vals_list)

    def write(self, vals):
        to_rename = self.browse()
        if "agreement_type" in vals or "company_id" in vals:
            to_rename = self.filtered(
                lambda agreement: (
                    agreement.agreement_type
                    != vals.get("agreement_type", agreement.agreement_type)
                    or agreement.company_id.id
                    != vals.get("company_id", agreement.company_id.id)
                )
            )
        res = super().write(vals)
        for agreement in to_rename:
            if agreement.state != "draft":
                raise UserError(
                    self.env._(
                        "You cannot change the Agreement Type or Company of an "
                        "agreement that is not a draft."
                    )
                )
            if agreement.agreement_type != "blanket_order":
                agreement.date_start = agreement.date_end = False
            agreement.name = agreement._next_name(
                agreement.agreement_type, agreement.company_id.id
            )
        return res

    def unlink(self):
        self.line_ids.unlink()
        return super().unlink()

    @api.ondelete(at_uninstall=False)
    def _unlink_if_draft_or_cancel(self) -> None:
        if any(agreement.state not in ("draft", "cancel") for agreement in self):
            raise UserError(
                self.env._("You can only delete draft or cancelled agreements.")
            )

    def action_confirm(self):
        self.check_singleton()
        if not self.line_ids:
            raise UserError(
                self.env._(
                    "You cannot confirm agreement '%(agreement)s' because it does "
                    "not contain any product lines.",
                    agreement=self.name,
                )
            )
        product_lines = self.line_ids.filtered("product_id")
        if any(line.price_unit <= 0.0 for line in product_lines):
            raise UserError(
                self.env._(
                    "You cannot confirm a blanket order with lines missing a price."
                )
            )
        if any(line.discount <= 0.0 for line in self.line_ids - product_lines):
            raise UserError(
                self.env._(
                    "A category line of an agreement needs the discount it grants."
                )
            )
        if self.commitment == "quantity" and any(
            line.product_qty <= 0.0 for line in product_lines
        ):
            raise UserError(
                self.env._(
                    "You cannot confirm a blanket order with lines missing a quantity."
                )
            )
        if self.commitment == "value" and self.amount_committed <= 0.0:
            raise UserError(
                self.env._(
                    "You cannot confirm a value commitment without the amount it "
                    "commits."
                )
            )
        self.line_ids._on_agreement_confirmed()
        self.state = "confirmed"
        _debug.lifecycle("agreement_confirmed", agreement=self)

    def action_draft(self):
        self.check_singleton()
        self.state = "draft"

    def action_done(self):
        if any(order.state == "draft" for order in self.order_ids):
            raise UserError(
                self.env._(
                    "To close this agreement, cancel its related quotations first.\n\n"
                    "Imagine the mess if someone confirms these duplicates: double "
                    "the order, double the trouble :)"
                )
            )
        self.line_ids._on_agreement_closed()
        self.write({"state": "done"})
        _debug.lifecycle("agreements_closed", agreements=self)

    def action_cancel(self):
        self.line_ids._on_agreement_closed()
        for agreement in self:
            agreement.order_ids.action_cancel()
            for order in agreement.order_ids:
                order.message_post(
                    body=self.env._(
                        "Cancelled by the agreement associated to this quotation."
                    )
                )
        self.state = "cancel"
        _debug.lifecycle("agreements_cancelled", agreements=self)

    def action_renew(self) -> dict:
        self.check_singleton()
        values = {"previous_agreement_id": self.id}
        if self.date_start and self.date_end:
            span = self.date_end - self.date_start
            values["date_start"] = self.date_end + relativedelta(days=1)
            values["date_end"] = values["date_start"] + span
        renewal = self.copy(values)
        for line, renewed in zip(self.line_ids, renewal.line_ids, strict=True):
            line.break_ids.copy({"agreement_id": renewal.id, "line_id": renewed.id})
        _debug.lifecycle("agreement_renewed", agreement=self, renewal=renewal)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": renewal.id,
            "view_mode": "form",
        }

    def action_view_renewal(self) -> dict:
        self.check_singleton()
        renewal = self.search([("previous_agreement_id", "=", self.id)], limit=1)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": renewal.id,
            "view_mode": "form",
        }

    @api.model
    def _cron_remind(self, expiry_days=30, consumed_threshold=90.0) -> None:
        today = fields.Date.context_today(self)
        expiring = self.search(
            [
                ("state", "=", "confirmed"),
                ("reminded_expiry", "=", False),
                ("date_end", "!=", False),
                ("date_end", "<=", today + relativedelta(days=expiry_days)),
            ]
        )
        for agreement in expiring:
            agreement._remind(
                self.env._(
                    "%(agreement)s ends on %(date)s: renew it or let it close.",
                    agreement=agreement.name,
                    date=agreement.date_end,
                )
            )
        expiring.reminded_expiry = True
        consumed = self.search(
            [
                ("state", "=", "confirmed"),
                ("reminded_consumption", "=", False),
                ("commitment", "!=", "price"),
                ("consumed_percent", ">=", consumed_threshold),
            ]
        )
        for agreement in consumed:
            agreement._remind(
                self.env._(
                    "%(agreement)s is %(percent)s%% consumed.",
                    agreement=agreement.name,
                    percent=round(agreement.consumed_percent),
                )
            )
        consumed.reminded_consumption = True
        _debug.lifecycle(
            "agreements_reminded", expiring=len(expiring), consumed=len(consumed)
        )

    def _remind(self, note) -> None:
        self.check_singleton()
        self.activity_schedule(
            "mail.mail_activity_data_todo",
            note=note,
            user_id=(self.user_id or self.env.user).id,
        )


class MixinAgreementLine(models.AbstractModel):
    _name = "mixin.agreement.line"
    _inherit = ["mixin.analytic"]
    _description = "Trade Agreement Line"
    _rec_name = "product_id"

    product_id = fields.Many2one(
        comodel_name="product.product",
        help="The product this line agrees a price for. Leave it empty to agree a "
        "discount on a whole category instead.",
    )
    product_category_id = fields.Many2one(
        comodel_name="product.category",
        string="Product Category",
        help="The category this line agrees a discount on: every product in it or "
        "below it that no product line of the agreement names.",
    )
    discount = fields.Float(
        string="Discount (%)",
        digits="Discount",
        help="On a category line, the discount its products take off their usual "
        "price.",
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit",
        compute="_compute_product_uom_id",
        precompute=True,
        store=True,
        readonly=False,
    )
    product_qty = fields.Float(
        string="Quantity",
        digits="Product Unit",
    )
    price_unit = fields.Float(
        string="Unit Price",
        min_display_digits="Product Price",
    )
    order_line_ids = fields.One2many(
        comodel_name="mixin.order.line.agreement",
        inverse_name="agreement_line_id",
        string="Order Lines",
    )
    qty_ordered = fields.Float(
        string="Ordered",
        digits="Product Unit",
        compute="_compute_ordered",
        store=True,
        help="What confirmed orders took from this line, less what was returned "
        "or credited back.",
    )
    qty_remaining = fields.Float(
        string="Remaining",
        digits="Product Unit",
        compute="_compute_ordered",
        store=True,
    )
    amount_ordered = fields.Monetary(
        string="Ordered Amount",
        currency_field="currency_id",
        compute="_compute_ordered",
        store=True,
    )
    currency_id = fields.Many2one(comodel_name="res.currency")
    break_ids = fields.One2many(
        comodel_name="mixin.agreement.line.break",
        inverse_name="line_id",
        string="Quantity Breaks",
    )

    @api.constrains("product_id", "product_category_id", "break_ids")
    def _check_product_or_category(self) -> None:
        for line in self:
            if bool(line.product_id) == bool(line.product_category_id):
                raise ValidationError(
                    self.env._(
                        "An agreement line names either a product or a product "
                        "category."
                    )
                )
            if line.product_category_id and line.break_ids:
                raise ValidationError(
                    self.env._(
                        "A category line grants a discount; quantity breaks price a "
                        "product line."
                    )
                )

    @api.depends("product_id", "product_category_id")
    def _compute_display_name(self):
        for line in self:
            line.display_name = (
                line.product_id.display_name or line.product_category_id.display_name
            )

    def _get_price_for_qty(self, qty):
        self.check_singleton()
        reached = self.break_ids.filtered(lambda rule: rule.min_qty <= qty)
        if not reached:
            return self.price_unit
        return max(reached, key=lambda rule: rule.min_qty).price_unit

    @api.depends("product_id")
    def _compute_product_uom_id(self):
        for line in self:
            line.product_uom_id = line.product_id.uom_id

    def _consumption_depends(self):
        depends = [
            "product_qty",
            "product_uom_id",
            "order_line_ids.state",
            "order_line_ids.product_qty",
            "order_line_ids.product_uom_id",
            "order_line_ids.price_subtotal",
            "order_line_ids.qty_transferred",
        ]
        OrderLine = self.env[self._fields["order_line_ids"].comodel_name]
        if "qty_invoiced" in OrderLine._fields:
            depends.append("order_line_ids.qty_invoiced")
        return depends

    @api.depends(lambda self: self._consumption_depends())
    def _compute_ordered(self) -> None:
        for line in self:
            agreement = line.agreement_id
            confirmed = line.order_line_ids.filtered(
                lambda order_line: (
                    order_line.state == "done" and not order_line.display_type
                )
            )
            qty_ordered = amount_ordered = 0.0
            for order_line in confirmed:
                released = order_line._get_released_qty()
                if (
                    line.product_uom_id
                    and order_line.product_uom_id._has_common_reference(
                        line.product_uom_id
                    )
                ):
                    qty_ordered += order_line.product_uom_id._get_quantity_in_unit(
                        released, line.product_uom_id
                    )
                if order_line.product_qty:
                    amount_ordered += order_line.currency_id._convert(
                        order_line.price_subtotal * released / order_line.product_qty,
                        agreement.currency_id,
                        agreement.company_id,
                        order_line.order_id.date_order
                        or fields.Date.context_today(line),
                    )
            line.qty_ordered = qty_ordered
            line.qty_remaining = line.product_qty - qty_ordered
            line.amount_ordered = amount_ordered

    def _on_agreement_confirmed(self) -> None:
        return None

    def _on_agreement_closed(self) -> None:
        return None

    def _prepare_order_line_values(self, product_qty, tax_ids):
        self.check_singleton()
        return {
            "product_id": self.product_id.id,
            "product_uom_id": self.product_uom_id.id,
            "product_qty": product_qty,
            "price_unit": self.price_unit,
            "tax_ids": [fields.Command.set(tax_ids)],
            "analytic_distribution": self.analytic_distribution,
        }
