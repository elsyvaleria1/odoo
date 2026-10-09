import base64
import logging
from collections import defaultdict
from copy import deepcopy
from datetime import UTC
from pprint import pformat
from random import randrange
from uuid import uuid4

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tools import float_is_zero, float_repr, float_round, formatLang, frozendict

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class PosOrder(models.Model):
    _name = "pos.order"
    _inherit = [
        "mixin.portal",
        "mixin.pos.bus",
        "mixin.pos.load",
        "mixin.mail.thread",
        "mixin.bearer.token",
    ]
    _description = "Point of Sale Orders"
    _order = "date_order desc, name desc, id desc"
    _pos_data_till_writes = frozendict(
        {"is_over_refund": False, "has_pricing_breach": False}
    )
    _mailing_enabled = True

    # the POS bus's and self-order's credential: a device's (decision G1),
    # kept sealed by mixin.bearer.token, not in clear. The customer's receipt
    # and payment links are access.link rows, receipt_token below (decision
    # POS-A)
    access_token = fields.Char(
        string="Security Token",
        compute="_compute_bearer_token",
        inverse="_inverse_bearer_token",
        search="_search_bearer_token",
        default=lambda self: str(uuid4()),
        store=False,
    )
    name = fields.Char(
        string="Order Ref",
        default="/",
        copy=False,
        readonly=True,
        required=True,
    )
    last_order_preparation_change = fields.Char(
        string="Last preparation change",
        help="Last printed state of the order",
    )
    date_order = fields.Datetime(
        string="Date",
        default=fields.Datetime.now,
        index=True,
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Employee",
        default=lambda self: self.env.uid,
        help="Employee who uses the cash register.",
    )
    amount_difference = fields.Monetary(
        string="Difference",
        readonly=True,
    )
    amount_tax = fields.Monetary(
        string="Taxes",
        readonly=True,
        required=True,
    )
    amount_total = fields.Monetary(
        string="Total",
        readonly=True,
        required=True,
    )
    amount_paid = fields.Monetary(
        string="Paid",
        required=True,
    )
    amount_return = fields.Monetary(
        string="Returned",
        readonly=True,
        required=True,
    )
    margin = fields.Monetary(
        compute="_compute_margins",
        store=True,
    )
    margin_percent = fields.Float(
        string="Margin (%)",
        digits=(12, 4),
        compute="_compute_margins",
        store=True,
    )
    is_total_cost_computed = fields.Boolean(
        compute="_compute_is_total_cost_computed",
        store=True,
        help="Allows to know if all the total cost of the order lines have already been computed",
    )
    lines = fields.One2many(
        comodel_name="pos.order.line",
        inverse_name="order_id",
        string="Order Lines",
        copy=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        index=True,
        readonly=True,
        required=True,
    )
    country_code = fields.Char(
        related="company_id.tax_config_id.account_fiscal_country_id.code"
    )
    pricelist_id = fields.Many2one(comodel_name="product.pricelist")
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        change_default=True,
        index="btree_not_null",
    )
    sequence_number = fields.Integer(
        copy=False,
        help="A session-unique sequence number for the order. Negative if generated from the client",
    )
    session_id = fields.Many2one(
        comodel_name="pos.session",
        index=True,
        domain="[('state', '=', 'opened')]",
    )
    config_id = fields.Many2one(
        comodel_name="pos.config",
        string="Point of Sale",
        compute="_compute_config_id",
        store=True,
        readonly=False,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="config_id.currency_id",
        string="Currency",
    )
    currency_rate = fields.Float(
        digits=0,
        compute="_compute_currency_rate",
        compute_sudo=True,
        store=True,
        readonly=True,
        help="The rate of the currency to the currency of rate applicable at the date of the order",
    )

    is_refund = fields.Boolean(
        default=False,
        readonly=True,
        help="Provenance: this order was created by refunding another. It "
        "carries no amount's sign -- `price_subtotal`, `total_cost` and "
        "`amount_total` each carry their own.",
    )
    is_over_refund = fields.Boolean(
        string="Refunds More Than Sold",
        copy=False,
        readonly=True,
    )
    has_pricing_breach = fields.Boolean(
        string="Breaks a Pricing Rule",
        copy=False,
        readonly=True,
        help="A paid line carries a discount, a price or taxes its point of sale "
        "does not let the cashier set.",
    )
    state = fields.Selection(
        selection=[
            ("draft", "New"),
            ("cancel", "Cancelled"),
            ("paid", "Paid"),
            ("done", "Posted"),
        ],
        string="Status",
        default="draft",
        index=True,
        copy=False,
        readonly=True,
    )

    account_move = fields.Many2one(
        comodel_name="account.move",
        string="Invoice",
        index="btree_not_null",
        copy=False,
        readonly=True,
    )
    picking_ids = fields.One2many(
        comodel_name="stock.picking",
        inverse_name="pos_order_id",
    )
    picking_count = fields.Count(count_of="picking_ids")
    failed_pickings = fields.Boolean(compute="_compute_failed_pickings")
    picking_type_id = fields.Many2one(
        comodel_name="stock.picking.type",
        related="session_id.config_id.picking_type_id",
        string="Operation Type",
        readonly=False,
    )
    reference_ids = fields.Many2many(
        comodel_name="stock.reference",
        relation="stock_reference_pos_order_rel",
        column1="pos_order_id",
        column2="reference_id",
    )
    preset_id = fields.Many2one(comodel_name="pos.preset")
    floating_order_name = fields.Char(string="Order Name")
    general_customer_note = fields.Text()
    internal_note = fields.Text()
    nb_print = fields.Integer(
        string="Number of Print",
        default=0,
        copy=False,
        readonly=True,
    )
    pos_reference = fields.Char(
        string="Receipt Number",
        index=True,
        copy=False,
        readonly=True,
    )
    sale_journal = fields.Many2one(
        comodel_name="account.journal",
        related="session_id.config_id.journal_id",
        string="Sales Journal",
        readonly=True,
        ondelete="restrict",
    )
    fiscal_position_id = fields.Many2one(
        comodel_name="account.fiscal.position",
        readonly=False,
    )
    payment_ids = fields.One2many(
        comodel_name="pos.payment",
        inverse_name="pos_order_id",
        string="Payments",
    )
    session_move_id = fields.Many2one(
        comodel_name="account.move",
        related="session_id.move_id",
        string="Session Journal Entry",
        copy=False,
        readonly=True,
    )
    to_invoice = fields.Boolean(
        string="To invoice",
        copy=False,
    )
    shipping_date = fields.Date()
    preset_time = fields.Datetime(
        string="Hour",
        help="Hour of the day for the order",
    )
    is_invoiced = fields.Boolean(compute="_compute_is_invoiced")
    is_tipped = fields.Boolean(
        string="Is this already tipped?",
        readonly=True,
    )
    tip_amount = fields.Monetary(readonly=True)
    refund_orders_count = fields.Integer(
        string="Number of Refund Orders",
        compute="_compute_refund_related_fields",
        help="Number of orders where items from this order were refunded",
    )
    refunded_order_id = fields.Many2one(
        comodel_name="pos.order",
        compute="_compute_refund_related_fields",
        help="Order from which items were refunded in this order",
    )
    has_refundable_lines = fields.Boolean(compute="_compute_has_refundable_lines")
    ticket_code = fields.Char(
        help="5 digits alphanumeric code to be used by portal user to request an invoice"
    )
    receipt_token = fields.Char(
        compute="_compute_receipt_token",
        help="The token of the link the receipt's QR code and the online payment "
        "carry; the link is an access.link row holding its hash.",
    )
    tracking_number = fields.Char(
        string="Order Number",
        copy=False,
        readonly=True,
    )
    uuid = fields.Char(
        default=lambda self: str(uuid4()),
        copy=False,
        readonly=True,
    )
    email = fields.Char(
        compute="_compute_contact_details",
        store=True,
        readonly=False,
    )
    phone_ids = fields.Many2many(
        comodel_name="phone.number",
        relation="pos_order_phone_number_rel",
        column1="order_id",
        column2="phone_number_id",
        string="Phone Numbers",
        compute="_compute_contact_details",
        inverse="_inverse_phone_ids",
        store=True,
        readonly=False,
    )
    is_edited = fields.Boolean(
        string="Edited",
        compute="_compute_is_edited",
    )
    has_deleted_line = fields.Boolean()
    order_edit_tracking = fields.Boolean(
        related="config_id.order_edit_tracking",
        readonly=True,
    )
    available_payment_method_ids = fields.Many2many(
        comodel_name="pos.payment.method",
        related="config_id.payment_method_ids",
        string="Available Payment Methods",
        store=False,
        readonly=True,
    )
    invoice_state = fields.Selection(
        selection=[
            ("invoiced", "Fully Invoiced"),
            ("to_invoice", "To Invoice"),
        ],
        string="Invoice Status",
        compute="_compute_invoice_state",
    )
    reversed_move_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="reversed_pos_order_id",
        string="Reversal Account Moves",
        help="List of account moves created when this POS order was reversed and invoiced after session close.",
    )
    source = fields.Selection(
        selection=[("pos", "Point of Sale")],
        string="Origin",
        default="pos",
    )

    _unique_uuid = models.Constraint(
        "unique (uuid)", "An order with this uuid already exists"
    )

    def _get_replacement_open_session(self, order):
        PosSession = self.env["pos.session"]
        closed_session = PosSession.browse(order.get("session_id"))

        _logger.warning(
            "Session %s (ID: %s) was closed but received order %s (total: %s) belonging to it",
            closed_session.name,
            closed_session.id,
            order.get("uuid"),
            order.get("amount_total"),
        )

        open_session = PosSession.search(
            [
                ("state", "not in", ("closed", "closing_control")),
                ("config_id", "=", closed_session.config_id.id),
            ],
            limit=1,
        )
        _debug.logic(
            "replacement_session_for_closed",
            order=order.get("uuid"),
            closed_session=closed_session,
            config=closed_session.config_id.id,
            open_session=open_session,
        )

        if open_session:
            _logger.warning(
                "Using open session %s for uuid number %s",
                open_session.name,
                order.get("uuid"),
            )
            return open_session

        raise UserError(
            self.env._(
                "No open session available. Please open a new session to capture the order."
            )
        )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("state", "=", "draft"), ("config_id", "=", config.id)]

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            "access_token",
            "receipt_token",
            "account_move",
            "amount_difference",
            "amount_paid",
            "amount_return",
            "amount_tax",
            "amount_total",
            "available_payment_method_ids",
            "company_id",
            "config_id",
            "country_code",
            "currency_id",
            "currency_rate",
            "date_order",
            "email",
            "failed_pickings",
            "fiscal_position_id",
            "floating_order_name",
            "general_customer_note",
            "has_deleted_line",
            "has_refundable_lines",
            "internal_note",
            "invoice_state",
            "is_edited",
            "is_invoiced",
            "is_over_refund",
            "has_pricing_breach",
            "is_refund",
            "is_tipped",
            "is_total_cost_computed",
            "last_order_preparation_change",
            "lines",
            "margin",
            "margin_percent",
            "name",
            "nb_print",
            "order_edit_tracking",
            "partner_id",
            "payment_ids",
            "phone_ids",
            "picking_count",
            "picking_ids",
            "picking_type_id",
            "pos_reference",
            "preset_id",
            "preset_time",
            "pricelist_id",
            "refund_orders_count",
            "refunded_order_id",
            "reversed_move_ids",
            "sale_journal",
            "sequence_number",
            "session_id",
            "session_move_id",
            "shipping_date",
            "source",
            "state",
            "reference_ids",
            "ticket_code",
            "tip_amount",
            "to_invoice",
            "tracking_number",
            "user_id",
            "uuid",
            "write_date",
        ]

    @api.model
    @_debug.perf.timed
    def _process_order(self, order, existing_order):
        """Persist a UI payload without consuming commands needed by extensions."""
        order = deepcopy(order)
        till_combo_shares = self._pop_till_combo_shares(order)
        draft = order.get("state") == "draft"
        pos_session = self.env["pos.session"].browse(order.get("session_id"))
        _debug.pipeline(
            "process_order",
            order=order.get("uuid"),
            existing=existing_order or None,
            draft=draft,
            state=order.get("state"),
            session=pos_session.id,
            session_state=pos_session.state,
            lines=len(order.get("lines") or ()),
            payments=len(order.get("payment_ids") or ()),
        )
        if pos_session.state in {"closing_control", "closed"}:
            pos_session = self._get_replacement_open_session(order)
            order["session_id"] = pos_session.id

        if not order.get("source"):
            order["source"] = "pos"

        if order.get("partner_id"):
            partner_id = self.env["res.partner"].browse(order["partner_id"])
            if not partner_id.exists():
                _debug.logic(
                    "partner_vanished_cleared",
                    order=order.get("uuid"),
                    partner=order["partner_id"],
                )
                order.update(
                    {
                        "partner_id": False,
                        "to_invoice": False,
                    }
                )

        order["company_id"] = pos_session.config_id.company_id.id

        if (
            self.env.context.get("current_order_uuid")
            and order["uuid"] == self.env.context["current_order_uuid"]
        ):
            _debug.logic("current_order_date_reset", order=order["uuid"])
            order["date_order"] = fields.Datetime.now()

        pos_order = False
        record_uuid_mapping = order.pop("relations_uuid_mapping", {})

        if not existing_order:
            pos_order = self.create(
                {
                    key: value
                    for key, value in order.items()
                    if key not in ("name", "access_token")
                }
            )
            _debug.pipeline("order_created", order=order.get("uuid"), record=pos_order)
        else:
            pos_order = existing_order

            if (
                order.get("session_id")
                and order["session_id"] != pos_order.session_id.id
            ):
                _debug.logic(
                    "order_session_moved",
                    order=order.get("uuid"),
                    from_session=pos_order.session_id.id,
                    to_session=order["session_id"],
                )
                pos_order.write({"session_id": order["session_id"]})

            for field in ["lines", "payment_ids"]:
                if order.get(field):
                    existing_ids = set(pos_order[field].ids)
                    existing_line_ids = {
                        line.uuid: line.id for line in pos_order[field]
                    }
                    rewritten = 0
                    for index, line in enumerate(order[field]):
                        if len(line) < 3:
                            continue
                        line_vals = line[2]
                        if (
                            line[0] == Command.CREATE
                            and line_vals.get("uuid") in existing_line_ids
                        ):
                            order[field][index] = Command.update(
                                existing_line_ids[line_vals["uuid"]], line_vals
                            )
                            rewritten += 1
                    _debug.logic(
                        "commands_create_to_update_by_uuid",
                        order=order.get("uuid"),
                        field=field,
                        commands=len(order[field]),
                        rewritten=rewritten,
                        existing=len(existing_ids),
                    )
                    pos_order.write({field: order[field]})
                    added_ids = set(pos_order[field].ids) - existing_ids
                    if added_ids:
                        _logger.info(
                            "Added %s %s to pos.order #%s",
                            field,
                            list(added_ids),
                            pos_order.id,
                        )
                    order[field] = []

            del order["uuid"]
            order.pop("access_token", None)
            if order.get("state") == "paid":
                _debug.logic(
                    "incoming_paid_state_kept",
                    order=pos_order.uuid,
                    server_state=pos_order.state,
                )
                order["state"] = pos_order.state
            if _debug.lifecycle.enabled:
                _debug.lifecycle(
                    "order_update",
                    order=pos_order.uuid,
                    record=pos_order,
                    fields=sorted(order),
                )
            pos_order.write(order)

        pos_order._link_uuid_relations(record_uuid_mapping)
        pos_order.lines._keep_till_combo_shares(till_combo_shares)
        self._check_single_refund_origin(pos_order.lines.refunded_orderline_id.order_id)

        pos_order = pos_order.with_company(pos_order.company_id)
        self._process_payment_lines(order, pos_order, draft)
        result = pos_order._process_saved_order(draft)
        if not draft:
            pos_order._flag_over_refund()
            pos_order._flag_pricing_breaches()
        return result

    @api.model
    def _pop_till_combo_shares(self, order) -> dict:
        shares = {}
        for command in order.get("lines") or ():
            if len(command) < 3 or not isinstance(command[2], dict):
                continue
            share = command[2].pop("combo_qty_per_parent", None)
            if share and command[2].get("uuid"):
                shares[command[2]["uuid"]] = share
        return shares

    def _link_uuid_relations(self, record_uuid_mapping) -> None:
        """Resolve deferred relations in batches, then write each owner once."""
        self.check_singleton()

        def as_list(uuids):
            return list(uuids) if isinstance(uuids, (list, tuple, set)) else [uuids]

        for model_name, mapping in record_uuid_mapping.items():
            owner_records = self.env[model_name].search(  # noqa: E8507 - one query per related model, over every owner uuid at once
                [("uuid", "in", mapping.keys())]
            )
            _debug.logic(
                "relations_uuid_mapping",
                order=self.uuid,
                model=model_name,
                owners=len(mapping),
                found=owner_records,
            )

            owners_by_uuid = {record.uuid: record for record in owner_records}
            relation_fields = self.env[model_name]._fields
            uuids_by_model = defaultdict(set)
            for field_names in mapping.values():
                for name, uuids in field_names.items():
                    uuids_by_model[relation_fields[name].comodel_name].update(
                        as_list(uuids)
                    )
            related_by_model = {}
            for comodel_name, uuids in uuids_by_model.items():
                related_by_model[comodel_name] = {
                    record.uuid: record
                    for record in self.env[comodel_name].search(  # noqa: E8507  one query per related model, over every field's uuid at once
                        [("uuid", "in", list(uuids))]
                    )
                }
            for uuid, field_names in mapping.items():
                owner = owners_by_uuid.get(uuid)
                if not owner:
                    continue
                values = {}
                for name, uuids in field_names.items():
                    params = relation_fields[name]
                    related = related_by_model[params.comodel_name]
                    if params.type in ["one2many", "many2many"]:
                        values[name] = [
                            Command.link(related[value].id)
                            for value in as_list(uuids)
                            if value in related
                        ]
                    else:
                        record = related.get(uuids)
                        values[name] = record.id if record else False
                if values:
                    owner.write(values)

    @_debug.perf.timed
    def _process_saved_order(self, draft):
        self.check_singleton()
        _debug.pipeline(
            "process_saved_order",
            order=self.uuid,
            draft=draft,
            state=self.state,
            to_invoice=self.to_invoice,
            amount_total=self.amount_total,
            amount_paid=self.amount_paid,
        )
        if not draft and self.state != "cancel":
            self.action_pos_order_paid()
            self._create_order_picking()
            self._update_total_cost_in_real_time()

        if self.to_invoice and self.state == "paid":
            if not self.config_id.invoice_journal_id:
                _logger.warning(
                    "Trying to create an invoice without any journal configured"
                )
                raise UserError(
                    self.env._("No invoice journal configured for this POS session.")
                )
            _debug.pipeline("saved_order_to_invoice", order=self.uuid)
            self._generate_pos_order_invoice()

        return self.id

    def _remove_payment_lines(self) -> None:
        self.check_singleton()
        self.payment_ids.unlink()

    def _process_payment_lines(self, order_vals, order, draft) -> None:
        amount_return = order_vals.get("amount_return") or 0.0
        prec_acc = order.currency_id.decimal_places

        if not draft and not float_is_zero(amount_return, prec_acc):
            cash_payment_method = order.session_id.config_id._get_cash_payment_method()
            _debug.logic(
                "change_recorded_on_cash_method",
                order=order.uuid,
                amount_return=amount_return,
                method=cash_payment_method,
            )
            if not cash_payment_method:
                raise UserError(
                    self.env._(
                        "No cash statement found for this session. Unable to record returned cash."
                    )
                )
            order.add_payment(
                {
                    "name": self.env._("return"),
                    "pos_order_id": order.id,
                    "amount": amount_return,
                    "payment_date": fields.Datetime.now(),
                    "payment_method_id": cash_payment_method.id,
                    "is_change": True,
                }
            )

        order._recompute_amounts()

    def _prepare_tax_base_line_values(self):
        result = []
        for order in self:
            result.extend(order.lines._prepare_tax_base_line_values() or [])
        return result

    @api.model
    def _prepare_invoice_line_vals(self, line_values, move_type):
        pos_line = line_values["record"]
        is_refund_order = pos_line.order_id._is_refund_order()
        qty_sign = (
            -1
            if (
                (move_type == "out_invoice" and is_refund_order)
                or (move_type == "out_refund" and not is_refund_order)
            )
            else 1
        )

        if line_values["product_id"].type == "combo":
            quantity = (
                int(line_values["quantity"])
                if line_values["quantity"] == int(line_values["quantity"])
                else line_values["quantity"]
            )
            return {
                "display_type": "line_section",
                "name": f"{line_values['product_id'].name} x {quantity}",
                "quantity": qty_sign * line_values["quantity"],
                "product_uom_id": line_values["uom_id"].id,
            }

        return {
            "product_id": line_values["product_id"].id,
            "quantity": qty_sign * line_values["quantity"],
            "discount": line_values["discount"],
            "price_unit": line_values["price_unit"],
            "name": line_values["name"],
            "tax_ids": [Command.set(line_values["tax_ids"].ids)],
            "product_uom_id": line_values["uom_id"].id,
            "extra_tax_data": self.env["account.tax"]._export_base_line_extra_tax_data(
                line_values
            ),
        }

    @_debug.perf.timed
    def _prepare_aml_vals(self, move_type):
        invoice_lines = []
        for order in self:
            line_values_list = order.with_context(
                invoicing=True
            )._prepare_tax_base_line_values()
            is_percentage = order.pricelist_id and any(
                order.pricelist_id.item_ids.filtered(
                    lambda rule: rule.compute_price == "percentage"
                )
            )
            _debug.logic(
                "invoice_base_lines",
                order=order.uuid,
                move_type=move_type,
                base_lines=len(line_values_list),
                percentage_pricelist=bool(is_percentage),
            )
            for line_values in line_values_list:
                line = line_values["record"]
                invoice_lines_values = order._prepare_invoice_line_vals(
                    line_values, move_type
                )
                invoice_lines.append((0, None, invoice_lines_values))

                if (
                    is_percentage
                    and order.currency_id.compare_amounts(
                        line.price_unit, line.product_id.lst_price
                    )
                    < 0
                ):
                    invoice_lines.append(
                        (
                            0,
                            None,
                            {
                                "name": self.env._(
                                    "Price discount from %(original_price)s to %(discounted_price)s",
                                    original_price=float_repr(
                                        line.product_id.lst_price,
                                        order.currency_id.decimal_places,
                                    ),
                                    discounted_price=float_repr(
                                        line.price_unit,
                                        order.currency_id.decimal_places,
                                    ),
                                ),
                                "display_type": "line_note",
                            },
                        )
                    )
                if line.customer_note:
                    invoice_lines.append(
                        (
                            0,
                            None,
                            {
                                "name": line.customer_note,
                                "display_type": "line_note",
                            },
                        )
                    )
            if order.general_customer_note:
                invoice_lines.append(
                    (
                        0,
                        None,
                        {
                            "name": order.general_customer_note,
                            "display_type": "line_note",
                        },
                    )
                )
        return invoice_lines

    def _get_pos_anglo_saxon_price_unit(self, product, quantity):
        moves = self.mapped("picking_ids.move_ids").filtered(
            lambda m: (
                m.is_valued
                and m.product_id.valuation == "real_time"
                and m.product_id.id == product.id
            )
        )
        return moves._get_price_unit()

    def get_preparation_change(self) -> dict:
        self.check_singleton()
        return {
            "last_order_preparation_change": self.last_order_preparation_change,
        }

    @api.model
    def _get_preparation_change_data(self, value) -> tuple:
        """Read the synchronization envelope without restricting extension fields."""
        if not value:
            return {}, False
        try:
            change = json_loads(value)
            if not isinstance(change, dict):
                raise ValueError("preparation change is not an object")
            metadata = change.get("metadata")
            if metadata is None:
                return change, False
            if not isinstance(metadata, dict):
                raise ValueError("preparation metadata is not an object")
            server_date = metadata.get("serverDate")
            if (
                server_date is not None
                and server_date is not False
                and not isinstance(server_date, str)
            ):
                raise ValueError("preparation serverDate is not a string")
            return change, fields.Datetime.to_datetime(server_date)
        except (TypeError, ValueError) as error:
            _debug.logic(
                "preparation_envelope_invalid",
                error=error,
                error_type=type(error).__name__,
            )
            raise ValidationError(
                self.env._(
                    "Preparation changes must be a JSON object with optional "
                    "metadata and a valid server date."
                )
            ) from error

    def _keep_newest_preparation_change(self, vals) -> None:
        self.check_singleton()
        local_change, local_date = self._get_preparation_change_data(
            vals.get("last_order_preparation_change")
        )
        change, server_date = self._get_preparation_change_data(
            self.last_order_preparation_change
        )
        if not change.get("metadata"):
            return

        if not local_change.get("metadata"):
            _debug.logic("preparation_change_no_metadata_server_kept", order=self.uuid)
            vals["last_order_preparation_change"] = self.last_order_preparation_change
            return

        keep_server = bool(server_date) and (not local_date or server_date > local_date)

        _debug.logic(
            "preparation_change_dates",
            order=self.uuid,
            server_date=server_date,
            local_date=local_date,
            kept="server" if keep_server else "local",
        )
        if keep_server:
            _logger.warning(
                "Preparation changes were outdated, probably linked to a synching issue."
            )
            vals["last_order_preparation_change"] = self.last_order_preparation_change
        else:
            local_change["metadata"]["serverDate"] = fields.Datetime.to_string(
                fields.Datetime.now()
            )
            vals["last_order_preparation_change"] = json_dumps(local_change)

    def _write_newest_preparation_change(self, vals) -> None:
        self.check_singleton()
        resolved = dict(vals)
        self._keep_newest_preparation_change(resolved)
        change = resolved.get("last_order_preparation_change")
        if change and change != self.last_order_preparation_change:
            self.write({"last_order_preparation_change": change})

    def _compute_receipt_token(self) -> None:
        links = (
            self.env["access.link"]
            ._record_links(
                self.filtered("id"),
                Domain("cause", "=", "notification")
                & Domain("audience", "=", "anyone")
                & Domain("role", "=", "view"),
            )
            .sorted("id", reverse=True)
        )
        shown = links._tokens()
        tokens = {}
        for link in links:
            if link.res_id not in tokens and link.id in shown:
                tokens[link.res_id] = shown[link.id]
        for order in self:
            order.receipt_token = tokens.get(order.id, False)

    def _issue_receipt_links(self) -> None:
        """A view link per order for its customer's receipt QR code and online
        payment, for as long as a receipt's link lives (decision B1: a year),
        reused while it lives."""
        tokens = self.env["access.link"]._issue_each(
            self, partner_field="partner_id", role="view", cause="notification"
        )
        for order in self:
            order._update_cache({"receipt_token": tokens[order.id]}, validate=False)

    def _receipt_token(self) -> str:
        self.check_singleton()
        self._issue_receipt_links()
        return self.receipt_token

    @api.depends("account_move")
    def _compute_invoice_state(self):
        for order in self:
            order.invoice_state = "invoiced" if order.account_move else "to_invoice"

    @api.depends("session_id")
    def _compute_config_id(self) -> None:
        for order in self:
            if order.session_id:
                order.config_id = order.session_id.config_id

    @api.depends(
        "lines.refund_orderline_ids",
        "lines.refund_orderline_ids.order_id.state",
        "lines.refunded_orderline_id",
    )
    def _compute_refund_related_fields(self) -> None:
        for order in self:
            order.refund_orders_count = len(order._get_refund_orders())
            order.refunded_order_id = next(
                iter(order.lines.refunded_orderline_id.order_id), False
            )

    @api.depends("lines.refunded_qty", "lines.qty")
    def _compute_has_refundable_lines(self) -> None:
        for order in self:
            order.has_refundable_lines = bool(order.lines._get_refundable_lines())

    @api.depends("account_move")
    def _compute_is_invoiced(self) -> None:
        for order in self:
            order.is_invoiced = bool(order.account_move)

    @api.depends("picking_ids", "picking_ids.state")
    def _compute_failed_pickings(self) -> None:
        for order in self:
            order.failed_pickings = bool(
                order.picking_ids.filtered(lambda p: p.state != "done")
            )

    @api.depends("date_order", "company_id", "currency_id", "company_id.currency_id")
    def _compute_currency_rate(self) -> None:
        for order in self:
            order.currency_rate = self.env["res.currency"]._get_conversion_rate(
                order.company_id.currency_id,
                order.currency_id,
                order.company_id,
                order.date_order.date(),
            )

    @api.depends("lines.is_total_cost_computed")
    def _compute_is_total_cost_computed(self) -> None:
        for order in self:
            order.is_total_cost_computed = False not in order.lines.mapped(
                "is_total_cost_computed"
            )

    @api.depends("partner_id")
    def _compute_contact_details(self) -> None:
        for order in self:
            order.email = order.partner_id.email or ""
            order.phone_ids = order.partner_id.phone_ids

    def _inverse_phone_ids(self) -> None:
        for order in self.filtered("partner_id"):
            missing = order.phone_ids - order.partner_id.phone_ids
            if missing:
                order.partner_id.phone_ids = [Command.link(p.id) for p in missing]

    def _update_total_cost_in_real_time(self) -> None:
        for order in self:
            lines = order.lines
            if not order._is_real_time_picking_required():
                storable_fifo_avco_lines = lines.filtered(
                    lambda l: l._is_product_storable_fifo_avco()
                )
                _debug.logic(
                    "cost_deferred_to_closing",
                    order=order.uuid,
                    lines=storable_fifo_avco_lines,
                )
                lines -= storable_fifo_avco_lines
            stock_moves = order.picking_ids.move_ids
            lines._update_total_cost(stock_moves)

    def _update_total_cost_at_session_closing(self, stock_moves) -> None:
        self.lines.filtered(
            lambda l: l._is_product_storable_fifo_avco()
        )._update_total_cost(stock_moves)

    @api.depends("lines.margin", "is_total_cost_computed")
    def _compute_margins(self) -> None:
        for order in self:
            if order.is_total_cost_computed:
                order.margin = sum(order.lines.mapped("margin"))
                amount_untaxed = order.currency_id.round(
                    sum(line.price_subtotal for line in order.lines)
                )
                order.margin_percent = (
                    not order.currency_id.is_zero(amount_untaxed)
                    and order.margin / amount_untaxed
                ) or 0
            else:
                order.margin = 0
                order.margin_percent = 0

    @api.onchange("payment_ids", "lines")
    def _onchange_amount_all(self) -> None:
        self._recompute_amounts()

    @_debug.perf.timed
    def _recompute_amounts(self) -> None:
        AccountTax = self.env["account.tax"]
        for order in self:
            if not order.currency_id:
                raise UserError(
                    self.env._(
                        "You can't: create a pos order from the backend interface, or unset the pricelist, or create a pos.order in a python test with Form tool, or edit the form view in studio if no PoS order exist"
                    )
                )
            base_lines = order.lines._prepare_tax_base_line_values()
            AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
            order.lines._write_subtotals(base_lines)

            cash_rounding = None
            if (
                order.config_id.cash_rounding
                and not order.config_id.only_round_cash_method
                and order.config_id.rounding_method
            ):
                cash_rounding = order.config_id.rounding_method

            tax_totals = AccountTax._get_tax_totals_summary(
                base_lines=base_lines,
                currency=order.currency_id,
                company=order.company_id,
                cash_rounding=cash_rounding,
            )
            refund_factor = -1 if order._is_refund_order() else 1
            amount_total = refund_factor * tax_totals["total_amount_currency"]
            payment_amounts = order._get_payment_amounts(amount_total)
            _debug.logic(
                "order_amounts",
                order=order.uuid,
                paid=payment_amounts["amount_paid"],
                amount_return=payment_amounts["amount_return"],
                tax=refund_factor * tax_totals["tax_amount_currency"],
                total=amount_total,
                cash_rounding=cash_rounding or None,
                refund=refund_factor < 0,
            )
            order.write(
                {
                    "amount_tax": refund_factor * tax_totals["tax_amount_currency"],
                    "amount_total": amount_total,
                    **payment_amounts,
                }
            )

    def _get_payment_amounts(self, amount_total) -> dict:
        self.check_singleton()
        amount_paid = sum(self.payment_ids.mapped("amount"))
        return {
            "amount_paid": amount_paid,
            "amount_return": -sum(
                min(payment.amount, 0.0) for payment in self.payment_ids
            ),
            "amount_difference": amount_paid - amount_total,
        }

    @api.depends("lines.is_edited", "has_deleted_line")
    def _compute_is_edited(self) -> None:
        for order in self:
            order.is_edited = (
                any(order.lines.mapped("is_edited")) or order.has_deleted_line
            )

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id:
            self.pricelist_id = self.partner_id.property_product_pricelist.id

    @api.ondelete(at_uninstall=False)
    def _unlink_except_draft_or_cancel(self):
        _debug.lifecycle("order_unlink", orders=self)
        order_to_cancel = self.env["pos.order"]
        for pos_order in self:
            if pos_order.state not in ["draft", "cancel"]:
                raise UserError(
                    self.env._(
                        "In order to delete a sale, it must be new or cancelled."
                    )
                )
            if pos_order.state == "draft":
                order_to_cancel |= pos_order
        if order_to_cancel:
            order_to_cancel.action_pos_order_cancel()

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "order_create",
                vals=len(vals_list),
                fields=sorted({k for vals in vals_list for k in vals}),
            )
        for vals in vals_list:
            if "last_order_preparation_change" in vals:
                self._get_preparation_change_data(vals["last_order_preparation_change"])
            if not vals.get("session_id"):
                raise UserError(
                    self.env._("A point of sale order must belong to a session.")
                )
            session = self.env["pos.session"].browse(vals["session_id"])
            self._update_values_from_session(session, vals)
        orders = super().create(vals_list)
        _debug.lifecycle("order_created_records", orders=orders)
        return orders

    def _update_sequence_number(self, session, values) -> None:
        values["sequence_number"] = (
            session.config_id.order_seq_id._next()
            .removeprefix(session.config_id.order_seq_id.prefix or "")
            .removesuffix(session.config_id.order_seq_id.suffix or "")
        )

    @api.model
    def _update_values_from_session(self, session, values):
        values.setdefault("pricelist_id", session.config_id.pricelist_id.id)
        values.setdefault(
            "fiscal_position_id", session.config_id.default_fiscal_position_id.id
        )
        values.setdefault("company_id", session.config_id.company_id.id)
        if session.config_id.use_presets and session.config_id.default_preset_id:
            values.setdefault("preset_id", session.config_id.default_preset_id.id)

        if not values.get("pos_reference"):
            reference, tracking_number = session.config_id._get_next_order_refs()
            values["pos_reference"] = reference
            values["tracking_number"] = tracking_number
            _debug.logic(
                "server_side_refs",
                order=values.get("uuid"),
                pos_reference=reference,
                tracking=tracking_number,
            )

        if not values.get("sequence_number"):
            self._update_sequence_number(session, values)

        return values

    def write(self, vals):
        vals = dict(vals)
        if "last_order_preparation_change" in vals:
            self._get_preparation_change_data(vals["last_order_preparation_change"])
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "order_write",
                orders=self,
                fields=sorted(vals),
                state=vals.get("state"),
            )
        if len(self) > 1 and (
            vals.get("payment_ids")
            or (vals.get("state") == "paid" and any(o.name == "/" for o in self))
            or (
                vals.get("has_deleted_line") is not None
                and any(o.has_deleted_line for o in self)
            )
        ):
            _debug.logic("order_write_fan_out", singleton_writes=len(self))
            for order in self:
                order.write(dict(vals))
            return True
        for order in self:
            if order.nb_print > 0 and any(
                command[0] in (Command.CREATE, Command.UPDATE)
                and command[2].get("payment_status")
                and command[2]["payment_status"] != "cancelled"
                for command in vals.get("payment_ids") or []
            ):
                raise UserError(
                    self.env._("You cannot change the payment of a printed order.")
                )
            if vals.get("state") and vals["state"] == "paid" and order.name == "/":
                session = (
                    self.env["pos.session"].browse(vals["session_id"])
                    if not order.session_id and vals.get("session_id")
                    else False
                )
                vals["name"] = order._get_order_name(session)
                _debug.logic("paid_name_assigned", order=order.uuid, name=vals["name"])
            if vals.get("has_deleted_line") is not None and order.has_deleted_line:
                _debug.logic("has_deleted_line_already_set", order=order.uuid)
                del vals["has_deleted_line"]
            allowed_vals = ["paid", "done"]
            if (
                vals.get("state")
                and vals["state"] not in allowed_vals
                and order.state in allowed_vals
            ):
                raise UserError(
                    self.env._(
                        "This order has already been paid. You cannot set it back to draft or edit it."
                    )
                )

        payment_changes = self._prepare_payment_change_log(vals)
        res = super().write(vals)
        for order in self:
            if vals.get("payment_ids"):
                order._recompute_amounts()
                payment_comparison = order.currency_id.compare_amounts(
                    order.amount_paid, order.amount_total
                )
                _debug.logic(
                    "after_payment_write",
                    order=order.uuid,
                    paid=order.amount_paid,
                    total=order.amount_total,
                    cmp=payment_comparison,
                    state=order.state,
                )
                if (
                    order.state not in ("paid", "done")
                    or order._is_payment_amount_valid()
                ):
                    continue
                is_negative_total = (
                    order.currency_id.compare_amounts(order.amount_total, 0) < 0
                )
                if payment_comparison < 0 or is_negative_total:
                    raise UserError(
                        self.env._(
                            "The paid amount is different from the total amount of the order."
                        )
                    )
                if payment_comparison > 0 and order.state == "paid":
                    payment_changes.append(
                        self.env._(
                            "Warning, the paid amount is higher than the total amount. (Difference: %s)",
                            formatLang(
                                self.env,
                                order.amount_paid - order.amount_total,
                                currency_obj=order.currency_id,
                            ),
                        )
                    )

        if len(payment_changes) > 0:
            body = self.env._("Payment changes:")
            body += self._markup_list_message(payment_changes)
            for order in self:
                if vals.get("payment_ids"):
                    order.message_post(body=body)

        return res

    def _prepare_payment_change_log(self, vals):
        if not vals.get("payment_ids"):
            return []

        message_list = []
        new_pms = vals.get("payment_ids", [])
        for new_pm in new_pms:
            orm_command = new_pm[0]

            if orm_command == 0:
                payment_method_id = self.env["pos.payment.method"].browse(
                    new_pm[2].get("payment_method_id")
                )
                amount = formatLang(
                    self.env, new_pm[2].get("amount"), currency_obj=self.currency_id
                )
                message_list.append(
                    self.env._(
                        "Added %(payment_method)s with %(amount)s",
                        payment_method=payment_method_id.name,
                        amount=amount,
                    )
                )
            elif orm_command == 1:
                pm_id = self.env["pos.payment"].browse(new_pm[1])
                old_pm = pm_id.payment_method_id.name
                old_amount = formatLang(
                    self.env, pm_id.amount, currency_obj=pm_id.currency_id
                )
                new_amount = False
                new_payment_method = False

                if new_pm[2].get("payment_method_id"):
                    new_payment_method = self.env["pos.payment.method"].browse(
                        new_pm[2].get("payment_method_id")
                    )
                if "amount" in new_pm[2]:
                    new_amount = formatLang(
                        self.env,
                        new_pm[2].get("amount"),
                        currency_obj=pm_id.currency_id,
                    )

                if new_payment_method and new_amount:
                    message_list.append(
                        self.env._(
                            "%(old_pm)s changed to %(new_pm)s and from %(old_amount)s to %(new_amount)s",
                            old_pm=old_pm,
                            new_pm=new_payment_method.name,
                            old_amount=old_amount,
                            new_amount=new_amount,
                        )
                    )
                elif new_payment_method:
                    message_list.append(
                        self.env._(
                            "%(old_pm)s changed to %(new_pm)s for %(old_amount)s",
                            old_pm=old_pm,
                            new_pm=new_payment_method.name,
                            old_amount=old_amount,
                        )
                    )
                elif new_amount:
                    message_list.append(
                        self.env._(
                            "Amount for %(old_pm)s changed from %(old_amount)s to %(new_amount)s",
                            old_amount=old_amount,
                            new_amount=new_amount,
                            old_pm=old_pm,
                        )
                    )
            elif orm_command == 2:
                pm_id = self.env["pos.payment"].browse(new_pm[1])
                amount = formatLang(
                    self.env, pm_id.amount, currency_obj=pm_id.currency_id
                )
                message_list.append(
                    self.env._(
                        "Removed %(payment_method)s with %(amount)s",
                        payment_method=pm_id.payment_method_id.name,
                        amount=amount,
                    )
                )

        return message_list

    def _markup_list_message(self, message):
        body = Markup("<ul>")
        for line in message:
            body += Markup("<li>")
            body += line
            body += Markup("</li>")
        body += Markup("</ul>")
        return body

    def _get_order_name(self, session=None) -> str:
        session = session or self.session_id
        if self.refunded_order_id.exists():
            return self.env._(
                "%(refunded_order)s REFUND", refunded_order=self.refunded_order_id.name
            )
        else:
            last_reference_part = self.get_reference_last_part()
            prefix = session.config_id.order_seq_id.prefix or session.config_id.name
            suffix = (
                f" - {session.config_id.order_seq_id.suffix}"
                if session.config_id.order_seq_id.suffix
                else ""
            )
            return f"{prefix} - {last_reference_part}{suffix}"

    def get_reference_last_part(self):
        return self.pos_reference.split("-")[-1]

    def action_stock_picking(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "stock.action_picking_tree_ready"
        )
        action["display_name"] = self.env._("Pickings")
        action["context"] = {}
        action["domain"] = [("id", "in", self.picking_ids.ids)]
        return action

    def action_view_invoice(self):
        invoices = self.account_move
        if len(invoices) == 1:
            return {
                "name": self.env._("Customer Invoice"),
                "view_mode": "form",
                "view_id": self.env.ref("account.view_move_form").id,
                "res_model": "account.move",
                "context": "{'move_type':'out_invoice'}",
                "type": "ir.actions.act_window",
                "res_id": self.account_move.id,
            }
        else:
            return {
                "name": self.env._("Customer Invoices"),
                "view_mode": "list,form",
                "res_model": "account.move",
                "type": "ir.actions.act_window",
                "domain": [("id", "in", invoices.ids)],
            }

    def action_create_invoices(self):
        return {
            "name": self.env._("Create Invoice(s)"),
            "view_mode": "form",
            "view_id": self.env.ref("point_of_sale.view_pos_make_invoice").id,
            "res_model": "wizard.pos.order.invoice",
            "target": "new",
            "type": "ir.actions.act_window",
            "context": {"dialog_size": "medium"},
        }

    def action_view_refunded_order(self) -> dict:
        return {
            "name": self.env._("Refunded Order"),
            "view_mode": "form",
            "view_id": self.env.ref("point_of_sale.view_pos_pos_form").id,
            "res_model": "pos.order",
            "type": "ir.actions.act_window",
            "res_id": self.refunded_order_id.id,
        }

    def action_view_refund_orders(self) -> dict:
        return {
            "name": self.env._("Refund Orders"),
            "view_mode": "list,form",
            "res_model": "pos.order",
            "type": "ir.actions.act_window",
            "domain": [("id", "in", self._get_refund_orders().ids)],
        }

    def _get_refund_orders(self):
        return self.mapped("lines.refund_orderline_ids.order_id").filtered(
            lambda o: o.state != "cancel"
        )

    def _get_amounts_due(self) -> tuple[float, ...]:
        """The amounts that settle the order, the one to propose first."""
        self.check_singleton()
        refunded = self.refunded_order_id
        if refunded and self.currency_id.is_zero(
            refunded.amount_total + self.amount_total
        ):
            # a full refund may give back what the customer paid, rounding included,
            # or the refund's own total, as the POS does
            return (-refunded.amount_paid, self.amount_total)
        return (self.amount_total,)

    def _is_refund_order(self):
        self.check_singleton()
        return self.is_refund or self.amount_total < 0.0

    def _is_cash_rounding_applicable(self) -> bool:
        config = self.config_id
        if not config.cash_rounding:
            return False
        return not config.only_round_cash_method or any(
            payment.payment_method_id.is_cash_count for payment in self.payment_ids
        )

    def _get_rounded_amount(self, amount, force_round=False):
        if self._is_cash_rounding_applicable() or (
            force_round and self.config_id.cash_rounding
        ):
            amount = float_round(
                amount,
                precision_rounding=self.config_id.rounding_method.rounding,
                rounding_method=self.config_id.rounding_method.rounding_method,
            )
        currency = self.currency_id
        return currency.round(amount) if currency else amount

    def _get_bank_account_id(self):
        bank_account_id = False
        amount_total = sum(order.amount_total for order in self)

        def get_first_allowed_bank(bank_account_ids):
            return bank_account_ids.filtered(lambda b: b.allow_out_payment)[:1]

        if amount_total <= 0 and self.partner_id.bank_account_ids:
            bank_account_id = get_first_allowed_bank(self.partner_id.bank_account_ids)

        elif amount_total >= 0 and self.payment_ids:
            journal_bank = self.payment_ids[
                0
            ].payment_method_id.journal_id.bank_account_id
            if journal_bank and journal_bank.allow_out_payment:
                bank_account_id = journal_bank

        if (
            not bank_account_id
            and amount_total >= 0
            and self.company_id.partner_id.bank_account_ids
        ):
            bank_account_id = get_first_allowed_bank(
                self.company_id.partner_id.bank_account_ids
            )

        return bank_account_id.id if bank_account_id else False

    @_debug.perf.timed
    def _create_invoice(self, move_vals):
        AccountMove = self.env["account.move"]

        invoice = (
            AccountMove.sudo()
            .with_company(self.company_id)
            .with_context(default_move_type=move_vals["move_type"])
            .create(move_vals)
        )
        currency = self.currency_id
        amount_total = sum(order.amount_total for order in self)
        payment_total = sum(order.amount_paid for order in self)
        _debug.pipeline(
            "invoice_created",
            orders=self,
            invoice=invoice,
            move_type=move_vals["move_type"],
            lines=len(move_vals.get("invoice_line_ids") or ()),
            amount_total=invoice.amount_total,
            orders_total=amount_total,
            orders_paid=payment_total,
        )

        if self.config_id.cash_rounding and invoice.invoice_cash_rounding_id:
            line_ids_commands = []
            rate = invoice.invoice_currency_rate
            sign = invoice.direction_sign
            amount_paid = (-1 if amount_total < 0.0 else 1) * payment_total
            difference_currency = sign * (amount_paid - invoice.amount_total)
            difference_balance = (
                invoice.company_currency_id.round(difference_currency / rate)
                if rate
                else 0.0
            )
            _debug.logic(
                "invoice_cash_rounding",
                orders=self,
                difference=difference_currency,
                balance=difference_balance,
                rate=rate,
            )
            if not currency.is_zero(difference_currency):
                rounding_line = invoice.line_ids.filtered(
                    lambda line: (
                        line.display_type == "rounding" and not line.tax_line_id
                    )
                )
                _debug.logic(
                    "invoice_rounding_line",
                    orders=self,
                    line=rounding_line,
                    action="updated" if rounding_line else "created",
                )
                if rounding_line:
                    line_ids_commands.append(
                        Command.update(
                            rounding_line.id,
                            {
                                "amount_currency": rounding_line.amount_currency
                                + difference_currency,
                                "balance": rounding_line.balance + difference_balance,
                            },
                        )
                    )
                else:
                    if difference_currency > 0.0:
                        account = invoice.invoice_cash_rounding_id.loss_account_id
                    else:
                        account = invoice.invoice_cash_rounding_id.profit_account_id
                    line_ids_commands.append(
                        Command.create(
                            {
                                "name": invoice.invoice_cash_rounding_id.name,
                                "amount_currency": difference_currency,
                                "balance": difference_balance,
                                "currency_id": invoice.currency_id.id,
                                "display_type": "rounding",
                                "account_id": account.id,
                            }
                        )
                    )
                existing_terms_line = invoice.line_ids.filtered(
                    lambda line: line.display_type == "payment_term"
                ).sorted(lambda line: -abs(line.amount_currency))[:1]
                line_ids_commands.append(
                    Command.update(
                        existing_terms_line.id,
                        {
                            "amount_currency": existing_terms_line.amount_currency
                            - difference_currency,
                            "balance": existing_terms_line.balance - difference_balance,
                        },
                    )
                )
                with AccountMove._check_balanced({"records": invoice}):
                    invoice.with_context(
                        skip_invoice_sync=True
                    ).line_ids = line_ids_commands
        body = self.env._(
            "This invoice has been created from the point of sale session:%s",
            Markup().join(Markup("%s ") % order._get_html_link() for order in self),
        )
        invoice.message_post(body=body)
        return invoice

    def _is_payment_amount_valid(self) -> bool:
        """Use the same rounding tolerance for settlement and subsequent edits."""
        self.check_singleton()
        return any(
            self._is_settled_at(amount_due) for amount_due in self._get_amounts_due()
        )

    def _is_settled_at(self, amount_due) -> bool:
        cash_rounding = self._is_cash_rounding_applicable()
        total = self._get_rounded_amount(amount_due)
        is_paid = self.currency_id.is_zero(total - self.amount_paid)
        _debug.logic(
            "payment_amount_check",
            order=self.uuid,
            total=self.amount_total,
            due=amount_due,
            rounded=total,
            paid=self.amount_paid,
            is_paid=is_paid,
            cash_rounding=cash_rounding,
        )

        if not is_paid and not cash_rounding:
            return False
        if not is_paid and cash_rounding:
            currency = self.currency_id
            rounding = self.config_id.rounding_method
            diff = currency.round(amount_due - self.amount_paid)
            if rounding.rounding_method == "HALF-UP":
                max_difference = currency.round(rounding.rounding / 2)
                is_within = currency.compare_amounts(abs(diff), max_difference) <= 0
            else:
                # UP and DOWN round off strictly less than one whole step
                max_difference = currency.round(rounding.rounding)
                is_within = currency.compare_amounts(abs(diff), max_difference) < 0
            _debug.logic(
                "rounding_tolerance",
                order=self.uuid,
                diff=diff,
                max_difference=max_difference,
                is_within=is_within,
            )
            return is_within
        return True

    def _check_refund_quantities(self) -> None:
        self.check_singleton()
        if over_refunded := self.lines.refunded_orderline_id._get_over_refunded_lines(
            self
        ):
            raise ValidationError(
                self.env._(
                    "You cannot refund more than was sold: %(lines)s",
                    lines=over_refunded._describe_with_order(),
                )
            )

    def _flag_over_refund(self) -> None:
        # the till has already handed the money back: record the refund and say so
        self.check_singleton()
        if over_refunded := self.lines.refunded_orderline_id._get_over_refunded_lines(
            self
        ):
            _logger.warning(
                "PoS order %s refunds more than was sold: %s",
                self.name,
                over_refunded.ids,
            )
            self.is_over_refund = True
            self.message_post(
                body=self.env._(
                    "This refund returns more than was sold: %(lines)s",
                    lines=over_refunded._describe_with_order(),
                )
            )

    def _may_cashier_set_discounts(self) -> bool:
        self.check_singleton()
        return self.config_id.manual_discount

    def _may_cashier_set_prices(self) -> bool:
        self.check_singleton()
        config = self.config_id
        return (
            not config.restrict_price_control
            or config.group_pos_manager_id in self.env.user.all_group_ids
        )

    def _flag_pricing_breaches(self) -> None:
        # the till has already taken the money: record the sale as made and say so
        self.check_singleton()
        breaches = self.lines._get_pricing_breaches()
        _debug.logic(
            "pricing_breaches",
            order=self.uuid,
            breaches={name: lines.ids for name, lines in breaches.items()} or None,
        )
        if not breaches:
            return
        _logger.warning(
            "PoS order %s breaks its pricing rules: %s",
            self.name,
            {name: lines.ids for name, lines in breaches.items()},
        )
        self.has_pricing_breach = True
        labels = self.lines._get_pricing_breach_labels()
        self.message_post(
            body=self.env._("This order breaks its point of sale's pricing rules:")
            + self._markup_list_message(
                [
                    self.env._(
                        "%(rule)s: %(lines)s",
                        rule=labels[name],
                        lines=lines._describe_with_order(),
                    )
                    for name, lines in breaches.items()
                ]
            )
        )

    def action_pos_order_paid(self):
        self.check_singleton()
        if not self._is_payment_amount_valid():
            raise UserError(self.env._("Order %s is not fully paid.", self.name))
        _debug.lifecycle("state_to_paid", order=self.uuid, state=self.state)
        self.write({"state": "paid"})

        return True

    def _prepare_invoice_vals(self):
        timezone = self.env.tz
        invoice_date = fields.Datetime.now()
        is_single_order = len(self) == 1

        if is_single_order and self.session_id.state != "closed":
            invoice_date = self.date_order

        pos_refunded_invoice_ids = [
            orderline.refunded_orderline_id.order_id.account_move.id
            for orderline in self.lines
            if orderline.refunded_orderline_id
            and orderline.refunded_orderline_id.order_id.account_move
        ]

        fiscal_position = self.fiscal_position_id
        pos_config = self.config_id
        move_type = (
            "out_invoice"
            if not any(order._is_refund_order() for order in self)
            else "out_refund"
        )
        invoice_payment_term_id = (
            self.partner_id.property_payment_term_id.id
            if self.partner_id.property_payment_term_id
            and any(p.payment_method_id.type == "pay_later" for p in self.payment_ids)
            else False
        )
        _debug.logic(
            "invoice_vals",
            orders=self,
            move_type=move_type,
            single=is_single_order,
            date=invoice_date,
            refunded_invoices=pos_refunded_invoice_ids,
            payment_term=invoice_payment_term_id,
            fiscal_position=fiscal_position.id,
            journal=pos_config.invoice_journal_id.id,
        )

        vals = {
            "invoice_origin": ", ".join(
                ref or "" for ref in self.mapped("pos_reference")
            ),
            "pos_refunded_invoice_ids": pos_refunded_invoice_ids,
            "pos_order_ids": self.ids,
            "ref": self.name if is_single_order else False,
            "journal_id": self.config_id.invoice_journal_id.id,
            "move_type": move_type,
            "partner_id": self.partner_id.address_get(["invoice"])["invoice"],
            "partner_shipping_id": self.partner_id.address_get(["delivery"])[
                "delivery"
            ],
            "bank_account_id": self._get_bank_account_id(),
            "currency_id": self.currency_id.id,
            "invoice_date": invoice_date.replace(tzinfo=UTC)
            .astimezone(timezone)
            .date(),
            "invoice_user_id": self.user_id.id,
            "fiscal_position_id": fiscal_position.id,
            "invoice_line_ids": self._prepare_aml_vals(move_type),
            "invoice_payment_term_id": invoice_payment_term_id,
        }
        if is_single_order and self.refunded_order_id.account_move:
            vals["ref"] = self.env._(
                "Reversal of: %s", self.refunded_order_id.account_move.name
            )
            vals["reversed_entry_id"] = self.refunded_order_id.account_move.id

        if self._is_cash_rounding_applicable():
            vals["invoice_cash_rounding_id"] = pos_config.rounding_method.id

        if any(order.floating_order_name for order in self):
            vals.update(
                {
                    "narration": ", ".join(
                        self.filtered("floating_order_name").mapped(
                            "floating_order_name"
                        )
                    )
                }
            )

        return vals

    def _prepare_product_aml_dict(
        self, base_line_vals, update_base_line_vals, rate, sign
    ):
        amount_currency = update_base_line_vals["amount_currency"]
        balance = self.company_id.currency_id.round(amount_currency * rate)
        order_line = base_line_vals["record"]
        return {
            "name": order_line.full_product_name,
            "product_id": order_line.product_id.id,
            "quantity": order_line.qty * sign,
            "account_id": base_line_vals["account_id"].id,
            "partner_id": base_line_vals["partner_id"].id,
            "currency_id": base_line_vals["currency_id"].id,
            "tax_ids": [Command.set(base_line_vals["tax_ids"].ids)],
            "tax_tag_ids": update_base_line_vals["tax_tag_ids"],
            "amount_currency": amount_currency,
            "balance": balance,
            "no_followup": False,
        }

    @_debug.perf.timed
    def _prepare_aml_values_list_per_nature(self):
        AccountTax = self.env["account.tax"]
        sign = 1 if self._is_refund_order() else -1
        commercial_partner = self.partner_id.commercial_partner_id
        company_currency = self.company_id.currency_id
        rate = self.currency_id._get_conversion_rate(
            self.currency_id, company_currency, self.company_id, self.date_order
        )

        base_lines = self._prepare_tax_base_line_values()
        AccountTax._add_tax_details_in_base_lines(base_lines, self.company_id)
        AccountTax._round_base_lines_tax_details(base_lines, self.company_id)
        AccountTax._add_accounting_data_in_base_lines_tax_details(
            base_lines, self.company_id
        )
        tax_results = AccountTax._prepare_tax_lines(base_lines, self.company_id)

        aml_vals_list_per_nature = defaultdict(list)

        total_amount_currency = self._add_tax_aml_vals(
            aml_vals_list_per_nature, tax_results
        )
        total_amount_currency += self._add_product_aml_vals(
            aml_vals_list_per_nature, tax_results, rate, sign
        )
        self._add_cash_rounding_aml_vals(
            aml_vals_list_per_nature,
            total_amount_currency,
            rate,
            sign,
            commercial_partner,
            company_currency,
        )

        self._add_stock_aml_vals(aml_vals_list_per_nature, commercial_partner)
        self._add_payment_term_aml_vals(aml_vals_list_per_nature, commercial_partner)
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "reversal_aml_per_nature",
                order=self.uuid,
                natures={k: len(v) for k, v in aml_vals_list_per_nature.items()},
                sign=sign,
                rate=rate,
                total=total_amount_currency,
            )

        return aml_vals_list_per_nature

    def _add_tax_aml_vals(self, aml_vals_list_per_nature, tax_results):
        total_amount_currency = 0.0
        for tax_line in tax_results["tax_lines_to_add"]:
            aml_vals_list_per_nature["tax"].append(
                {
                    **tax_line,
                    "display_type": "tax",
                }
            )
            total_amount_currency += tax_line["amount_currency"]
        return total_amount_currency

    def _add_product_aml_vals(self, aml_vals_list_per_nature, tax_results, rate, sign):
        total_amount_currency = 0.0
        for base_line_vals, update_base_line_vals in tax_results[
            "base_lines_to_update"
        ]:
            product_dict = self._prepare_product_aml_dict(
                base_line_vals, update_base_line_vals, rate, sign
            )
            aml_vals_list_per_nature["product"].append(product_dict)
            total_amount_currency += product_dict["amount_currency"]
        return total_amount_currency

    def _add_cash_rounding_aml_vals(
        self,
        aml_vals_list_per_nature,
        total_amount_currency,
        rate,
        sign,
        commercial_partner,
        company_currency,
    ) -> None:
        cash_rounding = self.config_id.rounding_method
        if cash_rounding and self._is_cash_rounding_applicable():
            if self.config_id.only_round_cash_method and any(
                not p.payment_method_id.is_cash_count for p in self.payment_ids
            ):
                total_payment_amount = self.currency_id.round(
                    sum(p.amount for p in self.payment_ids)
                )
                amount_currency = sign * self.currency_id.round(
                    self.currency_id.round(total_amount_currency) + total_payment_amount
                )
            else:
                amount_currency = cash_rounding.compute_difference(
                    self.currency_id, total_amount_currency
                )
            _debug.logic(
                "reversal_cash_rounding",
                order=self.uuid,
                strategy=cash_rounding.strategy,
                amount=amount_currency,
            )
            if not self.currency_id.is_zero(amount_currency):
                balance = company_currency.round(amount_currency * rate)

                if cash_rounding.strategy == "biggest_tax":
                    biggest_tax_aml_vals = None
                    for aml_vals in aml_vals_list_per_nature["tax"]:
                        if (
                            not biggest_tax_aml_vals
                            or self.currency_id.compare_amounts(
                                -sign * aml_vals["amount_currency"],
                                -sign * biggest_tax_aml_vals["amount_currency"],
                            )
                            > 0
                        ):
                            biggest_tax_aml_vals = aml_vals
                    if biggest_tax_aml_vals:
                        biggest_tax_aml_vals["amount_currency"] += amount_currency
                        biggest_tax_aml_vals["balance"] += balance
                elif cash_rounding.strategy == "add_invoice_line":
                    if -sign * amount_currency > 0.0 and cash_rounding.loss_account_id:
                        account_id = cash_rounding.loss_account_id.id
                    else:
                        account_id = cash_rounding.profit_account_id.id
                    aml_vals_list_per_nature["cash_rounding"].append(
                        {
                            "name": cash_rounding.name,
                            "account_id": account_id,
                            "partner_id": commercial_partner.id,
                            "currency_id": self.currency_id.id,
                            "amount_currency": amount_currency,
                            "balance": balance,
                            "display_type": "rounding",
                        }
                    )

    def _add_stock_aml_vals(self, aml_vals_list_per_nature, commercial_partner) -> None:
        if self.picking_ids.ids:
            stock_moves = (
                self.env["stock.move"]
                .sudo()
                .search(
                    [
                        ("picking_id", "in", self.picking_ids.ids),
                        ("product_id.valuation", "=", "real_time"),
                    ]
                )
            )
            _debug.logic(
                "stock_aml_real_time_moves",
                order=self.uuid,
                moves=len(stock_moves),
                pickings=self.picking_ids,
            )
            for stock_move in stock_moves:
                product_accounts = stock_move.product_id._get_product_accounts()
                expense_account = product_accounts["expense"]
                stock_account = product_accounts["stock_valuation"]
                balance = stock_move.value if stock_move.is_out else -stock_move.value
                aml_vals_list_per_nature["stock"].append(
                    {
                        "name": self.env._(
                            "Stock variation for %s", stock_move.product_id.name
                        ),
                        "account_id": expense_account.id,
                        "partner_id": commercial_partner.id,
                        "currency_id": self.company_id.currency_id.id,
                        "amount_currency": balance,
                        "balance": balance,
                    }
                )
                aml_vals_list_per_nature["stock"].append(
                    {
                        "name": self.env._(
                            "Stock variation for %s", stock_move.product_id.name
                        ),
                        "account_id": stock_account.id,
                        "partner_id": commercial_partner.id,
                        "currency_id": self.company_id.currency_id.id,
                        "amount_currency": -balance,
                        "balance": -balance,
                    }
                )

    def _add_payment_term_aml_vals(
        self, aml_vals_list_per_nature, commercial_partner
    ) -> None:
        for payment_id in self.payment_ids:
            is_split_transaction = payment_id.payment_method_id.split_transactions
            if is_split_transaction:
                reversed_move_receivable_account_id = (
                    self.partner_id.property_account_receivable_id
                )
            else:
                reversed_move_receivable_account_id = (
                    payment_id.payment_method_id.receivable_account_id
                    or self.company_id.account_config_id.account_default_pos_receivable_account_id
                )

            aml_vals_entry_found = [
                aml_entry
                for aml_entry in aml_vals_list_per_nature["payment_terms"]
                if aml_entry["account_id"] == reversed_move_receivable_account_id.id
                and not aml_entry["partner_id"]
            ]

            amount_currency = payment_id.amount
            balance = self.session_id._convert_amount_to_company_currency(
                payment_id.amount, self.date_order, False
            )

            if aml_vals_entry_found and not is_split_transaction:
                aml_vals_entry_found[0]["amount_currency"] += amount_currency
                aml_vals_entry_found[0]["balance"] += balance
            else:
                aml_vals_list_per_nature["payment_terms"].append(
                    {
                        "partner_id": commercial_partner.id
                        if is_split_transaction
                        else False,
                        "name": f"{reversed_move_receivable_account_id.code} {reversed_move_receivable_account_id.name}",
                        "account_id": reversed_move_receivable_account_id.id,
                        "currency_id": self.currency_id.id,
                        "amount_currency": amount_currency,
                        "balance": balance,
                        "display_type": "payment_term",
                    }
                )

    def _create_misc_reversal_move(self, payment_moves) -> None:
        self.check_singleton()
        aml_values_list_per_nature = self._prepare_aml_values_list_per_nature()
        move_lines = []
        for aml_values_list in aml_values_list_per_nature.values():
            for aml_values in aml_values_list:
                aml_values["balance"] = -aml_values["balance"]
                aml_values["amount_currency"] = -aml_values["amount_currency"]
                move_lines.append(aml_values)

        reversal_entry = (
            self.env["account.move"]
            .with_context(
                default_journal_id=self.config_id.journal_id.id,
                skip_invoice_sync=True,
                skip_invoice_line_sync=True,
            )
            .create(
                {
                    "journal_id": self.config_id.journal_id.id,
                    "date": fields.Date.context_today(self),
                    "ref": self.env._(
                        "Reversal of POS closing entry %(entry)s for order %(order)s from session %(session)s",
                        entry=self.session_move_id.name,
                        order=self.name,
                        session=self.session_id.name,
                    ),
                    "line_ids": [Command.create(aml_value) for aml_value in move_lines],
                    "reversed_pos_order_id": self.id,
                }
            )
        )
        reversal_entry.action_post()
        _debug.pipeline(
            "misc_reversal_posted",
            order=self.uuid,
            reversal=reversal_entry,
            lines=len(move_lines),
            closing_entry=self.session_move_id,
        )

        partner = self.partner_id.commercial_partner_id
        accounts = (
            self.company_id.account_config_id.account_default_pos_receivable_account_id
            | self.payment_ids.mapped("payment_method_id.receivable_account_id")
            | partner.property_account_receivable_id
        )

        candidate_lines = reversal_entry.line_ids
        if payment_moves.line_ids:
            candidate_lines |= payment_moves.line_ids
        else:
            candidate_lines |= self.session_move_id.line_ids.filtered(
                lambda l: (
                    l.partner_id == partner
                    and l.account_id == partner.property_account_receivable_id
                )
            )

        lines_by_account = {}
        for line in candidate_lines:
            if line.account_id in accounts and not line.reconciled:
                lines_by_account.setdefault(
                    line.account_id, self.env["account.move.line"]
                )
                lines_by_account[line.account_id] |= line
        if _debug.logic.enabled:
            _debug.logic(
                "reversal_reconciliation",
                order=self.uuid,
                payment_moves=payment_moves,
                candidates=len(candidate_lines),
                groups={a.code: len(l) for a, l in lines_by_account.items()},
            )
        for lines in lines_by_account.values():
            lines.reconcile()

    def action_pos_order_invoice(self) -> dict:
        self.check_singleton()
        if not (move := self.account_move):
            is_picking_created = self._is_real_time_picking_required()
            self.write({"to_invoice": True})
            _debug.logic(
                "invoice_real_time_picking",
                order=self.uuid,
                before=is_picking_created,
                after=self._is_real_time_picking_required(),
                session_state=self.session_id.state,
            )
            if (
                not is_picking_created
                and self._is_real_time_picking_required()
                and self.session_id.state != "closed"
            ):
                self._create_order_picking()
            # product and partner accounts are company-dependent fields
            move = self.with_company(self.company_id)._generate_pos_order_invoice()
        return {
            "name": self.env._("Customer Invoice"),
            "view_mode": "form",
            "view_id": self.env.ref("account.view_move_form").id,
            "res_model": "account.move",
            "context": "{'move_type':'out_invoice'}",
            "type": "ir.actions.act_window",
            "target": "current",
            "res_id": move.id,
        }

    def _prepare_invoice_post_context(self):
        return {"skip_invoice_sync": True}

    def _get_payments(self):
        return self.payment_ids.sudo().with_company(self.company_id)

    @_debug.perf.timed
    def _generate_pos_order_invoice(self):
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "generate_invoice",
                orders=self,
                states=self.mapped("state"),
            )
        if invalid_orders := self.filtered(lambda o: o.state not in ("paid", "done")):
            raise UserError(
                self.env._(
                    "The following orders cannot be invoiced because they are not"
                    " paid: %(orders)s",
                    orders=", ".join(invalid_orders.mapped("name")),
                )
            )
        if not self.env["res.company"]._with_locked_records(self, allow_raising=False):
            _debug.logic("invoicing_refused_locked", orders=self)
            raise UserError(
                self.env._(
                    "Some orders are already being invoiced. Please try again later."
                )
            )
        _debug.lifecycle("state_to_done", orders=self)
        self.state = "done"

        company = self.company_id
        # Portal defaults belong to the invoice, not its payment journal entries.
        invoice_order = self.with_context(
            {
                f"default_{name}": value
                for name, value in self.env.context.get(
                    "pos_ticket_invoice_values", {}
                ).items()
            }
        )
        invoice_vals = invoice_order._prepare_invoice_vals()
        invoice = invoice_order._create_invoice(invoice_vals)
        with _debug.perf("invoice_post", cr=self.env.cr, orders=self):
            invoice.sudo().with_company(company).with_context(
                **self._prepare_invoice_post_context()
            )._post()

        payment_moves_from_closed_sessions = {}
        all_payment_moves = self.env["account.move"].sudo()
        for session, orders in self.grouped("session_id").items():
            is_session_closed = session.state == "closed"
            for order in orders:
                order_payments = order._get_payments()
                payment_moves = order_payments._create_payment_moves(is_session_closed)
                all_payment_moves |= payment_moves
                if is_session_closed:
                    payment_moves_from_closed_sessions[order] = payment_moves
            _debug.pipeline(
                "session_payment_moves",
                orders=orders,
                session=session,
                closed=is_session_closed,
                payment_moves=all_payment_moves,
            )

        self._reconcile_invoice_payments(invoice, all_payment_moves)

        for order, payment_moves in payment_moves_from_closed_sessions.items():
            order._create_misc_reversal_move(payment_moves)

        if self.env.context.get("generate_pdf", True):
            with _debug.perf("invoice_pdf_send", cr=self.env.cr, orders=self):
                invoice.with_context(skip_invoice_sync=True)._generate_and_send()

        return invoice

    def _reconcile_invoice_payments(self, invoice, payment_moves) -> None:
        receivable_account = invoice.partner_id.commercial_partner_id.with_company(
            self.company_id
        ).property_account_receivable_id
        if not receivable_account.reconcile:
            _debug.logic(
                "receivable_not_reconcilable",
                orders=self,
                account=receivable_account.code,
            )
            return
        payment_receivable_lines = payment_moves.sudo().pos_payment_ids._get_receivable_lines_for_invoice_reconciliation(
            receivable_account
        )
        invoice_receivable_lines = invoice.sudo().line_ids.filtered(
            lambda line: line.account_id == receivable_account and not line.reconciled
        )
        _debug.pipeline(
            "reconcile_invoice",
            orders=self,
            invoice=invoice,
            payment_lines=payment_receivable_lines,
            invoice_lines=invoice_receivable_lines,
        )
        (payment_receivable_lines | invoice_receivable_lines).sudo().with_company(
            invoice.company_id
        ).reconcile()

    def action_pos_order_cancel(self):
        if self.env.context.get("active_ids"):
            orders = self.browse(self.env.context.get("active_ids"))
            order_is_in_futur = any(
                order.preset_time and order.preset_time.date() > fields.Date.today()
                for order in orders
            )
            if order_is_in_futur:
                raise UserError(
                    self.env._(
                        "The order delivery / pickup date is in the future. You cannot cancel it."
                    )
                )

        draft_orders = self._cancel_draft_orders()
        return {
            "pos.order": [
                row
                for config, orders in draft_orders.grouped("config_id").items()
                for row in self._load_pos_data_read(orders, config)
            ]
        }

    def _cancel_draft_orders(self):
        draft_orders = self.filtered(lambda order: order.state == "draft")
        _debug.lifecycle("order_cancel", draft=draft_orders, orders=self)
        if not draft_orders:
            return draft_orders
        draft_orders.write({"state": "cancel"})
        for config in draft_orders.config_id:
            config.notify_synchronisation(
                config.current_session_id.id,
                self.env.context.get("device_identifier", 0),
            )
        return draft_orders

    def _get_open_order(self, order):
        return self.env["pos.order"].search([("uuid", "=", order.get("uuid"))], limit=1)

    @staticmethod
    def _get_order_log_representation(order) -> dict:
        return {k: order.get(k) for k in ("name", "uuid")}

    @api.model
    @_debug.perf.timed
    def sync_from_ui(self, orders):
        sync_token = randrange(100_000_000)
        _logger.info(
            "PoS synchronisation #%d started for PoS orders references: %s",
            sync_token,
            [self._get_order_log_representation(order) for order in orders],
        )
        order_ids = []

        for order in orders:
            order = dict(order)
            order_log_name = self._get_order_log_representation(order)
            if _logger.isEnabledFor(logging.DEBUG):
                _logger.debug(
                    "PoS synchronisation #%d processing order %s order full data: %s",
                    sync_token,
                    order_log_name,
                    pformat(order),
                )

            refunded_orders = self._get_refunded_orders(order)
            self._check_single_refund_origin(refunded_orders)
            if len(refunded_orders) == 1:
                _debug.logic(
                    "sync_refunds",
                    sync=sync_token,
                    order=order.get("uuid"),
                    refunded=refunded_orders,
                )
                order_ids.append(refunded_orders[0].id)

            existing_order = self._get_open_order(order)
            # A delta can omit or delete its refund origin. Refresh the old origin
            # as well as the resulting one so clients receive its refunded quantity.
            order_ids.extend(existing_order.lines.refunded_orderline_id.order_id.ids)
            _debug.pipeline(
                "sync_order",
                sync=sync_token,
                order=order.get("uuid"),
                existing=existing_order,
                state=existing_order.state if existing_order else None,
                action="update"
                if existing_order and existing_order.state == "draft"
                else "create"
                if not existing_order
                else "ignore",
            )
            if existing_order and existing_order.state == "draft":
                existing_order._keep_newest_preparation_change(order)
                order_ids.append(self._process_order(order, existing_order))
                _logger.info(
                    "PoS synchronisation #%d order %s updated pos.order #%d",
                    sync_token,
                    order_log_name,
                    order_ids[-1],
                )
            elif not existing_order:
                order_ids.append(self._process_order(order, False))
                _logger.info(
                    "PoS synchronisation #%d order %s created pos.order #%d",
                    sync_token,
                    order_log_name,
                    order_ids[-1],
                )
            else:
                existing_order._write_newest_preparation_change(order)
                order_ids.append(existing_order.id)
                _logger.info(
                    "PoS synchronisation #%d order %s sync ignored for existing PoS order %s (state: %s)",
                    sync_token,
                    order_log_name,
                    existing_order,
                    existing_order.state,
                )

        pos_order_ids = self.env["pos.order"].browse(list(dict.fromkeys(order_ids)))
        pos_order_ids |= pos_order_ids.lines.refunded_orderline_id.order_id

        for order in pos_order_ids:
            order._pos_bus_get_or_create_token()
        pos_order_ids._issue_receipt_links()
        if not self.env.context.get("preparation"):
            for order_config in pos_order_ids.config_id:
                order_config.notify_synchronisation(
                    order_config.current_session_id.id,
                    self.env.context.get("device_identifier", 0),
                )
        else:
            _debug.logic("sync_preparation_no_bus_notification", sync=sync_token)

        _logger.info("PoS synchronisation #%d finished", sync_token)
        with _debug.perf("sync_read_pos_data", cr=self.env.cr, sync=sync_token):
            return pos_order_ids._read_pos_data_per_config(orders)

    @api.model
    def read_pos_orders(self, domain=False):
        orders = self.search(domain)
        return orders._read_pos_data_per_config([]) if orders else {"pos.order": []}

    def _read_pos_data_per_config(self, data) -> dict:
        if not self:
            return self.read_pos_data(data, False)
        result = {}
        seen = set()
        for config, orders in self.grouped("config_id").items():
            for model, rows in orders.read_pos_data(data, config).items():
                merged = result.setdefault(model, [])
                for row in rows:
                    key = (model, row.get("id"))
                    if key in seen:
                        continue
                    if key[1] is not None:
                        seen.add(key)
                    merged.append(row)
        _debug.logic("read_pos_data_per_config", orders=self, configs=self.config_id)
        return result

    _READ_POS_DATA_MODELS = (
        "pos.order",
        "pos.session",
        "pos.payment",
        "pos.order.line",
        "pos.pack.operation.lot",
        "product.attribute.custom.value",
        "account.move",
    )

    @_debug.perf.timed
    def read_pos_data(self, data, config):
        if not config:
            return {model: [] for model in self._READ_POS_DATA_MODELS}
        sudo_self = self.sudo()
        account_moves = (
            sudo_self.account_move
            | sudo_self.payment_ids.account_move_id
            | sudo_self.session_move_id
        )
        return {
            "pos.order": self._load_pos_data_read(self, config),
            "pos.session": [],
            "pos.payment": self.env["pos.payment"]._load_pos_data_read(
                self.payment_ids, config
            ),
            "pos.order.line": self.env["pos.order.line"]._load_pos_data_read(
                self.lines, config
            ),
            "pos.pack.operation.lot": self.env[
                "pos.pack.operation.lot"
            ]._load_pos_data_read(self.lines.pack_lot_ids, config),
            "product.attribute.custom.value": self.env[
                "product.attribute.custom.value"
            ]._load_pos_data_read(self.lines.custom_attribute_value_ids, config),
            "account.move": self.env["account.move"]
            .sudo()
            ._load_pos_data_read(account_moves, config),
        }

    @api.model
    def _check_single_refund_origin(self, refunded_orders) -> None:
        if len(refunded_orders) > 1:
            raise ValidationError(
                self.env._("You can only refund products from the same order.")
            )

    @api.model
    def _get_refunded_orders(self, order):
        refunded_orderline_ids = [
            line[2]["refunded_orderline_id"]
            for line in order.get("lines") or []
            if line[0] in (Command.CREATE, Command.UPDATE)
            and line[2].get("refunded_orderline_id")
        ]
        return (
            self.env["pos.order.line"].browse(refunded_orderline_ids).mapped("order_id")
        )

    def _is_real_time_picking_required(self):
        return (
            not self.session_id.update_stock_at_closing
            or self._is_real_time_picking_forced()
        )

    def _is_real_time_picking_forced(self):
        return (
            self.company_id.account_config_id.anglo_saxon_accounting and self.to_invoice
        )

    @_debug.perf.timed
    def _create_order_picking(self) -> None:
        self.check_singleton()
        if self.picking_ids:
            _debug.logic(
                "picking_already_exists",
                order=self.uuid,
                pickings=self.picking_ids,
            )
            return
        if self.shipping_date:
            _debug.pipeline(
                "picking_via_procurement",
                order=self.uuid,
                shipping_date=self.shipping_date,
            )
            self.sudo().lines._launch_stock_rule_from_pos_order_lines()
        elif self._is_real_time_picking_required():
            picking_type = self.config_id.picking_type_id
            if self.partner_id.property_stock_customer:
                destination_id = self.partner_id.property_stock_customer.id
            elif not picking_type or not picking_type.default_location_dest_id:
                destination_id = (
                    self.env["stock.warehouse"]._get_partner_locations()[0].id
                )
            else:
                destination_id = picking_type.default_location_dest_id.id
            _debug.pipeline(
                "real_time_picking",
                order=self.uuid,
                picking_type=picking_type,
                dest=destination_id,
                lines=len(self.lines),
            )

            pickings = (
                self.env["stock.picking"]
                .sudo()
                ._create_picking_from_pos_order_lines(
                    destination_id,
                    self.lines,
                    picking_type,
                    self.partner_id,
                    pos_order=self,
                    pos_session=self.session_id,
                    origin=self.name,
                )
            )
            pickings.backorder_ids.write(
                {
                    "pos_session_id": self.session_id.id,
                    "pos_order_id": self.id,
                    "origin": self.name,
                }
            )
            if _debug.pipeline.enabled:
                _debug.pipeline(
                    "pickings_created",
                    order=self.uuid,
                    pickings=pickings,
                    backorders=pickings.backorder_ids,
                )
        else:
            _debug.logic("no_picking_stock_at_closing", order=self.uuid)

    def add_payment(self, data) -> None:
        self.check_singleton()
        _debug.lifecycle(
            "add_payment",
            order=self.uuid,
            method=data.get("payment_method_id"),
            amount=data.get("amount"),
            change=data.get("is_change", False),
        )
        self.env["pos.payment"].create(data)
        self.write(self._get_payment_amounts(self.amount_total))

    def _prepare_refund_values(self, current_session) -> dict:
        self.check_singleton()
        pos_reference, tracking_number = (
            current_session.config_id._get_next_order_refs()
        )
        return {
            "name": self.env._("%(name)s REFUND", name=self.name),
            "session_id": current_session.id,
            "date_order": fields.Datetime.now(),
            "pos_reference": pos_reference,
            "lines": False,
            "amount_paid": 0,
            "is_total_cost_computed": False,
            "is_refund": True,
            "tracking_number": tracking_number,
        }

    def _refund(self):
        refund_orders = self.env["pos.order"]
        for order in self:
            current_session = order.session_id.config_id.current_session_id
            if not current_session:
                raise UserError(
                    self.env._(
                        "To return product(s), you need to open a session in the POS %s",
                        order.session_id.config_id.display_name,
                    )
                )
            refund_order = order.copy(order._prepare_refund_values(current_session))
            _debug.lifecycle(
                "refund_order_created",
                order=order.uuid,
                refund=refund_order,
                session=current_session,
            )
            for line in order.lines._get_refundable_lines():
                refund_lots = line.pack_lot_ids.copy()
                line.copy(line._prepare_refund_values(refund_order, refund_lots))
            refund_orders |= refund_order
            refund_order.config_id.notify_synchronisation(current_session.id, 0)
        refund_orders._recompute_amounts()
        return refund_orders

    def action_refund(self):
        self.check_singleton()
        return {
            "name": self.env._("Return Products"),
            "view_mode": "form",
            "res_model": "pos.order",
            "res_id": self._refund().ids[0],
            "view_id": False,
            "context": self.env.context,
            "type": "ir.actions.act_window",
            "target": "current",
        }

    def action_send_mail(self):
        template = self.env["mail.template"].search(
            [("model", "=", self._name)], limit=1
        )
        return {
            "name": self.env._("Send Email"),
            "view_mode": "form",
            "res_model": "wizard.mail.message.send",
            "type": "ir.actions.act_window",
            "context": {
                "default_composition_mode": "mass_mail",
                "default_res_ids": self.ids,
                "default_template_id": template.id,
            },
            "target": "new",
        }

    def action_send_receipt(self, email, ticket_image, basic_image) -> None:
        self.check_singleton()
        _debug.lifecycle(
            "receipt_send",
            order=self.uuid,
            email=email,
            basic=bool(basic_image),
            invoice=bool(self.account_move),
        )
        self.email = email
        mail_template_id = "point_of_sale.email_template_pos_receipt"
        mail_template = self.env.ref(mail_template_id, raise_if_not_found=False)
        if not mail_template:
            raise UserError(
                self.env._(
                    "The mail template with xmlid %s has been deleted.",
                    mail_template_id,
                )
            )
        mail_template.send_mail(
            self.id,
            force_send=True,
            email_values={
                "email_to": email,
                "attachment_ids": self._create_mail_attachments(
                    self.name, ticket_image, basic_image
                ),
            },
        )

    def _create_mail_attachments(self, name, ticket, basic_ticket):
        self.check_singleton()
        attachment_values = [
            {
                "name": f"Receipt-{name}.jpg",
                "datas": ticket,
                "mimetype": "image/jpeg",
            }
        ]

        if basic_ticket:
            attachment_values.append(
                {
                    "name": f"Receipt-{name}-1.jpg",
                    "datas": basic_ticket,
                    "mimetype": "image/jpeg",
                }
            )

        if self.account_move:
            invoice_pdf, _ = self.env["ir.actions.report"]._render_qweb_pdf(
                "account.account_invoices", self.account_move.id
            )
            attachment_values.append(
                {
                    "name": f"{name}.pdf",
                    "datas": base64.b64encode(invoice_pdf),
                    "mimetype": "application/pdf",
                }
            )

        attachments = self.env["ir.attachment"].create(
            [
                {"type": "binary", "res_model": self._name, "res_id": self.id, **values}
                for values in attachment_values
            ]
        )
        _debug.lifecycle(
            "receipt_attachments", order=self.uuid, attachments=attachments.ids
        )
        return [Command.link(attachment.id) for attachment in attachments]

    @api.model
    def remove_from_ui(self, server_ids):
        orders = self.search([("id", "in", server_ids), ("state", "=", "draft")])
        _debug.lifecycle("remove_from_ui", asked=server_ids, draft=orders)
        orders._cancel_draft_orders()
        orders.mapped("payment_ids").sudo().unlink()
        orders.sudo().unlink()
        return orders.ids

    @api.model
    @_debug.perf.timed
    def search_paid_order_ids(self, config_id, domain, limit, offset) -> dict:
        pos_config = self.env["pos.config"].browse(config_id)
        real_domain = Domain(domain) & (
            Domain("state", "not in", ("draft", "cancel"))
            & Domain("config_id", "in", [config_id] + pos_config.trusted_config_ids.ids)
        )
        orders = self.search(
            real_domain, limit=limit, offset=offset, order="create_date desc"
        )
        last_write = {order.id: order.write_date for order in orders}

        def fold(order_id, write_date):
            if write_date and write_date > last_write.get(order_id, write_date):
                last_write[order_id] = write_date

        PosOrderLine = self.env["pos.order.line"]
        for order, write_date in PosOrderLine._read_group(
            [("order_id", "in", orders.ids)],
            groupby=["order_id"],
            aggregates=["write_date:max"],
        ):
            fold(order.id, write_date)

        refund_groups = PosOrderLine._read_group(
            [("refunded_orderline_id.order_id", "in", orders.ids)],
            groupby=["refunded_orderline_id"],
            aggregates=["write_date:max"],
        )
        refunded_lines = PosOrderLine.browse(
            [line.id for line, _write_date in refund_groups]
        )
        order_id_by_line = {line.id: line.order_id.id for line in refunded_lines}
        for line, write_date in refund_groups:
            fold(order_id_by_line.get(line.id), write_date)

        return {
            "ordersInfo": [(order.id, last_write[order.id]) for order in orders],
            "totalCount": self.search_count(real_domain),
        }

    def _send_order(self):
        pass

    def _prepare_pos_log(self, body):
        return body
