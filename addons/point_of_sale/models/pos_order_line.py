from collections import defaultdict
from datetime import UTC
from itertools import groupby
from typing import Self
from uuid import uuid4

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, float_compare, frozendict

_debug = DebugLog(__name__)


class PosOrderLine(models.Model):
    _name = "pos.order.line"
    _description = "Point of Sale Order Lines"
    _rec_name = "product_id"
    _inherit = ["mixin.pos.load"]
    _pos_data_till_writes = frozendict({"combo_qty_per_parent": True})
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        related="order_id.company_id",
        string="Company",
    )
    name = fields.Char(
        string="Line No",
        copy=False,
        required=True,
    )
    notice = fields.Char(string="Discount Notice")
    product_id = fields.Many2one(
        comodel_name="product.product",
        change_default=True,
        required=True,
        domain=[("sale_ok", "=", True)],
    )
    attribute_value_ids = fields.Many2many(
        comodel_name="product.template.attribute.value",
        string="Selected Attributes",
    )
    custom_attribute_value_ids = fields.One2many(
        comodel_name="product.attribute.custom.value",
        inverse_name="pos_order_line_id",
        string="Custom Values",
        store=True,
        readonly=False,
    )
    price_unit = fields.Float(
        string="Unit Price",
        digits=0,
    )
    qty = fields.Float(
        string="Quantity",
        digits="Product Unit",
        default=1,
    )
    price_subtotal = fields.Monetary(
        string="Tax Excl.",
        readonly=True,
        required=True,
        help="Signed like `qty`, as `total_cost` and `amount_total` are.",
    )
    price_subtotal_incl = fields.Monetary(
        string="Tax Incl.",
        readonly=True,
        required=True,
        help="Signed like `qty`, as `price_subtotal` is.",
    )
    price_extra = fields.Float(string="Price extra")
    price_type = fields.Selection(
        selection=[
            ("original", "Original"),
            ("manual", "Manual"),
            ("automatic", "Automatic"),
        ],
        default="original",
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
    total_cost = fields.Float(
        string="Total cost",
        min_display_digits="Product Price",
        readonly=True,
    )
    price_cost = fields.Float(
        string="Cost",
        readonly=True,
        help="Unit cost behind `total_cost`, which stores `qty * cost` converted "
        "to the line currency. Reporting needs the two separately.",
    )
    is_total_cost_computed = fields.Boolean(
        help="Allows to know if the total cost has already been computed or not"
    )
    discount = fields.Float(
        string="Discount (%)",
        digits=0,
        default=0.0,
    )
    discount_barcode = fields.Char(
        copy=False,
        help="The discount barcode the till scanned for this line's discount.",
    )
    approved_pricing = fields.Json(
        copy=False,
        readonly=True,
        help="The price and discount a sync whose cashier could set them last "
        "set on this line.",
    )
    order_id = fields.Many2one(
        comodel_name="pos.order",
        string="Order Ref",
        index=True,
        required=True,
        ondelete="cascade",
    )
    tax_ids = fields.Many2many(
        comodel_name="account.tax",
        string="Taxes",
        readonly=True,
    )
    tax_ids_after_fiscal_position = fields.Many2many(
        comodel_name="account.tax",
        string="Taxes to Apply",
        compute="_compute_tax_ids_after_fiscal_position",
    )
    pack_lot_ids = fields.One2many(
        comodel_name="pos.pack.operation.lot",
        inverse_name="pos_order_line_id",
        string="Lot/serial Number",
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        related="product_id.uom_id",
        string="Product Unit",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="order_id.currency_id",
    )
    full_product_name = fields.Char()
    customer_note = fields.Char()
    refund_orderline_ids = fields.One2many(
        comodel_name="pos.order.line",
        inverse_name="refunded_orderline_id",
        string="Refund Order Lines",
        help="Orderlines in this field are the lines that refunded this orderline.",
    )
    refunded_orderline_id = fields.Many2one(
        comodel_name="pos.order.line",
        string="Refunded Order Line",
        index="btree_not_null",
        help="If this orderline is a refund, then the refunded orderline is specified in this field.",
    )
    refunded_qty = fields.Float(
        string="Refunded Quantity",
        compute="_compute_refunded_qty",
        help="Number of items refunded in this orderline.",
    )
    uuid = fields.Char(
        default=lambda self: str(uuid4()),
        copy=False,
        readonly=True,
    )
    note = fields.Char(string="Product Note")

    combo_parent_id = fields.Many2one(
        comodel_name="pos.order.line",
        index="btree_not_null",
    )
    combo_line_ids = fields.One2many(
        comodel_name="pos.order.line",
        inverse_name="combo_parent_id",
        string="Combo Lines",
    )
    combo_qty_per_parent = fields.Float(
        string="Quantity per Combo",
        compute="_compute_combo_qty_per_parent",
        precompute=True,
        store=True,
        readonly=False,
        help="Quantity of this combo item in one combo; kept while the combo is at zero.",
    )

    combo_item_id = fields.Many2one(comodel_name="product.combo.item")
    is_edited = fields.Boolean(
        string="Edited",
        default=False,
    )
    extra_tax_data = fields.Json()

    _unique_uuid = models.Constraint(
        "unique (uuid)", "An order line with this uuid already exists"
    )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [
            ("order_id", "in", [order["id"] for order in data["pos.order"]]),
            ("product_id.active", "=", True),
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            "qty",
            "attribute_value_ids",
            "custom_attribute_value_ids",
            "price_unit",
            "uuid",
            "price_subtotal",
            "price_subtotal_incl",
            "order_id",
            "note",
            "price_type",
            "product_id",
            "discount",
            "tax_ids",
            "pack_lot_ids",
            "customer_note",
            "refunded_qty",
            "price_extra",
            "full_product_name",
            "refunded_orderline_id",
            "combo_parent_id",
            "combo_line_ids",
            "combo_item_id",
            "combo_qty_per_parent",
            "refund_orderline_ids",
            "extra_tax_data",
            "discount_barcode",
            "write_date",
        ]

    @api.depends("qty", "combo_parent_id.qty")
    def _compute_combo_qty_per_parent(self) -> None:
        for line in self:
            if line.combo_parent_id.qty:
                line.combo_qty_per_parent = line.qty / line.combo_parent_id.qty

    def _keep_till_combo_shares(self, shares_by_uuid) -> None:
        if not shares_by_uuid:
            return
        at_zero = self.filtered(
            lambda line: (
                line.uuid in shares_by_uuid
                and line.combo_parent_id
                and not line.combo_parent_id.qty
            )
        )
        _debug.logic("combo_shares_from_till", lines=at_zero, shares=shares_by_uuid)
        for share, lines in at_zero.grouped(
            lambda line: shares_by_uuid[line.uuid]
        ).items():
            lines.combo_qty_per_parent = share

    @api.depends(
        "refund_orderline_ids",
        "refund_orderline_ids.qty",
        "refund_orderline_ids.order_id.state",
    )
    def _compute_refunded_qty(self) -> None:
        for orderline in self:
            refund_order_line = orderline.refund_orderline_ids.filtered(
                lambda l: l.order_id.state != "cancel"
            )
            orderline.refunded_qty = -sum(refund_order_line.mapped("qty"))

    def read_for_refund(self, field_names) -> dict:
        drafts = self.refund_orderline_ids.filtered(
            lambda refund: refund.order_id.state == "draft"
        )
        _debug.logic("read_for_refund", lines=self, drafts=drafts)
        return {
            "lines": self.read(field_names, load=False),
            "draft_refunds": [
                {
                    "line_id": refund.refunded_orderline_id.id,
                    "order_uuid": refund.order_id.uuid,
                    "order": refund.order_id.pos_reference or refund.order_id.name,
                    "till": refund.order_id.config_id.name,
                    "qty": -refund.qty,
                }
                for refund in drafts
            ],
        }

    def _get_over_refunded_lines(self, refund_order) -> Self:
        self._serialize_refund_settlements()
        digits = self.env["decimal.precision"].get_precision("Product Unit")

        def settled_refund_qty(line):
            refunds = line.refund_orderline_ids.filtered(
                lambda refund: (
                    refund.order_id == refund_order
                    or refund.order_id.state in ("paid", "done")
                )
            )
            return -sum(refunds.mapped("qty"))

        over_refunded = self.filtered(
            lambda line: (
                line.qty > 0
                and float_compare(
                    settled_refund_qty(line), line.qty, precision_digits=digits
                )
                > 0
            )
        )
        _debug.logic("refunded_qty_check", lines=self, over_refunded=over_refunded)
        return over_refunded

    def _serialize_refund_settlements(self) -> None:
        if not self:
            return
        self.lock_for_update(allow_referencing=True, wait=True)
        self.env.cr.execute(
            SQL(
                "UPDATE %s SET write_date = write_date WHERE id = ANY(%s)",
                SQL.identifier(self._table),
                self.ids,
            )
        )
        _debug.logic("refund_settlements_serialized", lines=self)

    def _describe_with_order(self) -> str:
        return ", ".join(
            f"{line.full_product_name or line.product_id.display_name}"
            f" ({line.order_id.name})"
            for line in self
        )

    def _get_pricing_breach_labels(self) -> dict[str, str]:
        return {
            "discount": self.env._("a discount the point of sale does not allow"),
            "price_unit": self.env._("a price other than the pricelist's"),
            "tax_ids": self.env._("taxes other than the product's"),
        }

    def _get_pricing_exemptions(self) -> dict[Self, set[str]]:
        tip_products = self.order_id.config_id.tip_product_id
        return {
            line: (
                {"price_unit"}
                if line.combo_parent_id
                or line.combo_line_ids
                or line.product_id in tip_products
                else set()
            )
            for line in self
        }

    def _get_pricing_breaches(self) -> dict[str, Self]:
        if not self:
            return {}
        self.order_id.check_singleton()
        checks = {
            "discount": "_has_allowed_discount",
            "price_unit": "_has_allowed_price",
            "tax_ids": "_has_allowed_taxes",
        }
        exemptions = self._get_pricing_exemptions()
        breaches = defaultdict(self.browse)
        for line in self:
            for name in checks.keys() - exemptions[line]:
                if not getattr(line, checks[name])():
                    breaches[name] |= line
        return {name: breaches[name] for name in checks if name in breaches}

    def _approve_pricing(self, previous) -> None:
        if not self:
            return
        order = self.order_id
        order.check_singleton()
        names = [
            name
            for name, may in (
                ("price_unit", order._may_cashier_set_prices()),
                ("discount", order._may_cashier_set_discounts()),
            )
            if may
        ]
        for line in self if names else ():
            before = previous.get(line.uuid, {})
            approved = dict(line.approved_pricing or {})
            for name in names:
                if before.get(name) != line[name] and (
                    name != "discount" or line.discount
                ):
                    approved[name] = line[name]
            if approved != (line.approved_pricing or {}):
                _debug.logic(
                    "line_pricing_approved",
                    order=order.uuid,
                    line=line.uuid,
                    approved=approved,
                )
                line.approved_pricing = approved

    def _is_approved(self, field_name, digits) -> bool:
        self.check_singleton()
        approved = self.approved_pricing or {}
        return field_name in approved and not float_compare(
            self[field_name], approved[field_name], precision_digits=digits
        )

    def _has_allowed_discount(self) -> bool:
        self.check_singleton()
        digits = self.env["decimal.precision"].get_precision("Discount")
        return (
            not float_compare(
                self.discount,
                self.refunded_orderline_id.discount,
                precision_digits=digits,
            )
            or self._is_approved("discount", digits)
            or self._is_discount_from_barcode(digits)
        )

    def _is_discount_from_barcode(self, digits) -> bool:
        self.check_singleton()
        if not self.discount_barcode:
            return False
        nomenclature = self.company_id.barcodes_config_id.nomenclature_id
        fallback = self.order_id.config_id.fallback_nomenclature_id
        if nomenclature.is_gs1_nomenclature and fallback:
            nomenclature = fallback
        parsed = (
            nomenclature.parse_barcode(self.discount_barcode) if nomenclature else {}
        )
        return (
            isinstance(parsed, dict)
            and parsed.get("type") == "discount"
            and not float_compare(
                self.discount, parsed["value"], precision_digits=digits
            )
        )

    def _has_allowed_price(self) -> bool:
        self.check_singleton()
        digits = self.env["decimal.precision"].get_precision("Product Price")
        if self._is_approved("price_unit", digits):
            return True
        allowed = (
            [self.refunded_orderline_id.price_unit]
            if self.refunded_orderline_id
            else self._get_pricelist_prices()
        )
        return any(
            not float_compare(self.price_unit, price, precision_digits=digits)
            for price in allowed
        )

    def _has_allowed_taxes(self) -> bool:
        self.check_singleton()
        if self.refunded_orderline_id:
            return self.tax_ids == self.refunded_orderline_id.tax_ids
        fiscal_position = self.order_id.fiscal_position_id
        return fiscal_position.map_tax(self.tax_ids) == fiscal_position.map_tax(
            self._get_product_taxes()
        )

    def _get_product_taxes(self):
        self.check_singleton()
        if not self.order_id.config_id._allows_taxes():
            return self.env["account.tax"]
        return self.product_id.taxes_id.filtered_domain(
            self.env["account.tax"]._get_domain_company_compatible(self.company_id)
        )

    def _get_pricelist_prices(self) -> list[float]:
        self.check_singleton()
        order = self.order_id
        product = self.product_id.with_context(
            **self.product_id._prepare_product_price_context(self.attribute_value_ids)
        )
        quantities = {self.qty}
        if product.tracking != "none":
            quantities.add(
                sum(
                    order.lines.filtered(
                        lambda line: line.product_id == product
                    ).mapped("qty")
                )
            )
        return [
            order.pricelist_id._get_product_price(
                product, quantity, currency=order.currency_id, date=order.date_order
            )
            for quantity in quantities
        ]

    def _get_refundable_lines(self) -> Self:
        digits = self.env["decimal.precision"].get_precision("Product Unit")
        return self.filtered(
            lambda line: (
                float_compare(line.qty, line.refunded_qty, precision_digits=digits) > 0
            )
        )

    def _prepare_refund_values(self, refund_order, refund_lots) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("%(name)s REFUND", name=self.name),
            "qty": -(self.qty - self.refunded_qty),
            "order_id": refund_order.id,
            "pack_lot_ids": refund_lots,
            "is_total_cost_computed": False,
            "refunded_orderline_id": self.id,
        }

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        unnamed = [vals for vals in vals_list if not vals.get("name")]
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "line_create",
                vals=len(vals_list),
                unnamed=len(unnamed),
                fields=sorted({k for vals in vals_list for k in vals}),
            )
        if unnamed:
            PosOrder = self.env["pos.order"]
            orders = PosOrder.browse(
                [vals["order_id"] for vals in unnamed if vals.get("order_id")]
            ).exists()
            sequence_by_order_id = {
                order.id: order.session_id.config_id.order_line_seq_id
                for order in orders
            }
            order_by_id = {order.id: order for order in orders}
            for vals in unnamed:
                order_id = vals.get("order_id")
                order = order_by_id.get(order_id, PosOrder)
                sequence = sequence_by_order_id.get(order_id, self.env["ir.sequence"])
                if not sequence:
                    raise UserError(
                        self.env._(
                            "The point of sale %(config)s has no order-line"
                            " sequence, so its order lines cannot be numbered.",
                            config=order.session_id.config_id.display_name
                            or order.display_name,
                        )
                    )
                vals["name"] = sequence.sudo()._next()
        return super().create(vals_list)

    def write(self, vals):
        new_qty = vals.get("qty")
        if _debug.lifecycle.enabled:
            _debug.lifecycle("line_write", lines=self, fields=sorted(vals))
        if new_qty is not None:
            digits = self.env["decimal.precision"].get_precision("Product Unit")
            edited = self.browse()
            bodies_per_order = defaultdict(list)
            for line in self:
                if not line.order_id.config_id.order_edit_tracking:
                    continue
                if float_compare(new_qty, line.qty, digits) >= 0:
                    continue
                _debug.logic(
                    "line_qty_decrease_tracked",
                    order=line.order_id.uuid,
                    line=line.id,
                    qty=line.qty,
                    new_qty=new_qty,
                )
                edited |= line
                body = self.env._(
                    "%(product_name)s: Ordered quantity: %(old_qty)s",
                    product_name=line.full_product_name,
                    old_qty=line.qty,
                )
                bodies_per_order[line.order_id].append(
                    body + Markup("&rarr;") + str(new_qty)
                )
            for order, bodies in bodies_per_order.items():
                body = (
                    bodies[0]
                    if len(bodies) == 1
                    else order._markup_list_message(bodies)
                )
                order.message_post(body=order._prepare_pos_log(body))
            edited.is_edited = True
        return super().write(vals)

    @api.model
    def get_existing_lots(self, company_id, config_id, product_id):
        self.check_access("read")
        pos_config = self.env["pos.config"].browse(config_id)
        if not pos_config:
            raise UserError(self.env._("No PoS configuration found"))

        company_id = pos_config.company_id.id
        src_loc = pos_config.picking_type_id.default_location_src_id

        domain = [
            "|",
            ("company_id", "=", False),
            ("company_id", "=", company_id),
            ("product_id", "=", product_id),
            ("location_id", "in", src_loc.child_internal_location_ids.ids),
            ("quantity", ">", 0),
            ("trace_id", "!=", False),
        ]

        groups = (
            self.sudo()
            .env["stock.quant"]
            ._read_group(
                domain=domain, groupby=["trace_id"], aggregates=["quantity:sum"]
            )
        )

        result = []
        for lot_recordset, total_quantity in groups:
            if lot_recordset:
                result.append(
                    {
                        "id": lot_recordset.id,
                        "name": lot_recordset.name,
                        "product_qty": total_quantity,
                    }
                )

        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_order_state(self) -> None:
        if self.filtered(lambda x: x.order_id.state not in ["draft", "cancel"]):
            raise UserError(
                self.env._(
                    "You can only unlink PoS order lines that are related to orders in new or cancelled state."
                )
            )

    @api.onchange("price_unit", "tax_ids", "qty", "discount", "product_id")
    def _onchange_amount_line_all(self) -> None:
        priced = self.filtered("product_id")
        for line, subtotals in priced._get_subtotals().items():
            line.update(subtotals)

    def _get_subtotals(self) -> dict[Self, dict[str, float]]:
        AccountTax = self.env["account.tax"]
        subtotals = {}
        for order, lines in self.grouped("order_id").items():
            base_lines = [
                line._prepare_base_line_for_taxes_computation() for line in lines
            ]
            AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
            subtotals |= lines._get_subtotals_from_base_lines(base_lines)
        return subtotals

    def _get_subtotals_from_base_lines(
        self, base_lines
    ) -> dict[Self, dict[str, float]]:
        AccountTax = self.env["account.tax"]
        subtotals = {}
        for base_line in base_lines:
            line = base_line["record"].with_env(self.env)
            if line not in self:
                continue
            tax_details = base_line["tax_details"]
            sign = -1 if line.order_id._is_refund_order() else 1
            subtotals[line] = {
                "price_subtotal": sign
                * (
                    tax_details["total_excluded_currency"]
                    + tax_details["delta_total_excluded_currency"]
                ),
                "price_subtotal_incl": sign
                * AccountTax._measure_base_lines_total([base_line])[0],
            }
        return subtotals

    def _write_subtotals(self, base_lines) -> None:
        subtotals = self._get_subtotals_from_base_lines(base_lines)
        if len(subtotals) < len(self):
            subtotals = self._get_subtotals()
        for line, values in subtotals.items():
            currency = line.currency_id
            stale = {
                name: value
                for name, value in values.items()
                if not currency or currency.compare_amounts(line[name], value)
            }
            if stale:
                _debug.logic(
                    "line_subtotals_recomputed",
                    order=line.order_id.uuid,
                    line=line.uuid,
                    sent={name: line[name] for name in stale},
                    computed=stale,
                )
                line.update(stale)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            price = self.order_id.pricelist_id._get_product_price(
                self.product_id, self.qty or 1.0, currency=self.currency_id
            )
            self.tax_ids = self._get_product_taxes()
            tax_ids_after_fiscal_position = self.order_id.fiscal_position_id.map_tax(
                self.tax_ids
            )
            self.price_unit = self.env["account.tax"]._fix_tax_included_price_company(
                price, self.tax_ids, tax_ids_after_fiscal_position, self.company_id
            )
            self._onchange_amount_line_all()

    @api.depends("order_id", "order_id.fiscal_position_id", "tax_ids")
    def _compute_tax_ids_after_fiscal_position(self) -> None:
        for line in self:
            line.tax_ids_after_fiscal_position = (
                line.order_id.fiscal_position_id.map_tax(line.tax_ids)
            )

    def _prepare_reference_vals(self):
        return {
            "name": self.order_id.name,
            "pos_order_ids": [Command.link(self.order_id.id)],
        }

    def _prepare_procurement_vals(self):
        self.check_singleton()
        if self.order_id.shipping_date:
            from_zone = self.env.tz
            shipping_date = fields.Datetime.to_datetime(self.order_id.shipping_date)
            shipping_date = shipping_date.replace(tzinfo=from_zone)
            date_deadline = shipping_date.astimezone(UTC).replace(tzinfo=None)
        else:
            date_deadline = self.order_id.date_order

        return {
            "date_planned": date_deadline,
            "date_deadline": date_deadline,
            "route_ids": self.order_id.config_id.route_id,
            "warehouse_id": self.order_id.config_id.warehouse_id,
            "partner_id": self.order_id.partner_id.id,
            "product_description_variants": self.full_product_name,
            "company_id": self.order_id.company_id,
            "reference_ids": self.order_id.reference_ids,
        }

    @_debug.perf.timed
    def _launch_stock_rule_from_pos_order_lines(self):

        procurements = []
        for line in self:
            line = line.with_company(line.company_id)
            if line.product_id.type != "consu":
                _debug.logic(
                    "line_procurement_skipped",
                    order=line.order_id.uuid,
                    line=line.id,
                    product_type=line.product_id.type,
                )
                continue

            reference_ids = line.order_id.reference_ids
            if not reference_ids:
                reference_ids = (
                    self.env["stock.reference"]
                    .sudo()
                    .create(line._prepare_reference_vals())
                )
                line.order_id.reference_ids = [Command.set(reference_ids.ids)]
                _debug.pipeline(
                    "stock_reference_created",
                    order=line.order_id.uuid,
                    references=reference_ids,
                )

            values = line._prepare_procurement_vals()
            product_qty = line.qty

            procurement_uom = line.product_id.uom_id
            procurements.append(
                self.env["stock.rule"].Procurement(
                    line.product_id,
                    product_qty,
                    procurement_uom,
                    line.order_id.partner_id.property_stock_customer,
                    line.name,
                    line.order_id.name,
                    line.order_id.company_id,
                    values,
                )
            )
        _debug.pipeline(
            "procurements_built", procurements=len(procurements), orders=self.order_id
        )
        if procurements:
            with _debug.perf("stock_rule_run", cr=self.env.cr, orders=self.order_id):
                self.env["stock.rule"].run(procurements)

        orders = self.mapped("order_id")
        for order in orders:
            pickings_to_confirm = order.picking_ids
            _debug.pipeline(
                "pickings_to_confirm", order=order.uuid, pickings=pickings_to_confirm
            )
            if pickings_to_confirm:
                tracked_lines = order.lines.filtered(
                    lambda l: l.product_id.tracking != "none"
                )
                lines_by_tracked_product = groupby(
                    sorted(tracked_lines, key=lambda l: l.product_id.id),
                    key=lambda l: l.product_id.id,
                )
                pickings_to_confirm.action_confirm()
                for product_id, lines in lines_by_tracked_product:
                    lines = self.env["pos.order.line"].concat(*lines)
                    moves = pickings_to_confirm.move_ids.filtered_domain(
                        [("product_id", "=", product_id)]
                    )
                    moves.move_line_ids.unlink()
                    moves._add_move_lines_from_pos_order_lines(
                        lines, are_quantities_done=False
                    )
                    moves._recompute_state()
        return True

    def _is_product_storable_fifo_avco(self) -> bool:
        self.check_singleton()
        return self.product_id.is_storable and self.product_id.cost_method in [
            "fifo",
            "average",
        ]

    def _get_product_cost_with_moves(self, moves):
        self.check_singleton()
        return moves._get_price_unit()

    @_debug.perf.timed
    def _update_total_cost(self, stock_moves) -> None:
        moves_and_cost_by_product = {}
        for line in self.filtered(lambda l: not l.is_total_cost_computed):
            line = line.with_company(line.company_id)
            product = line.product_id
            cost_currency = product.sudo().cost_currency_id
            key = (product, line.company_id)
            if key not in moves_and_cost_by_product:
                moves = (
                    line._get_stock_moves_to_consider(stock_moves, product)
                    if stock_moves
                    else None
                )
                moves_and_cost_by_product[key] = (
                    moves,
                    line._get_product_cost_with_moves(moves)
                    if moves and line._is_product_storable_fifo_avco()
                    else None,
                )
            moves, moves_cost = moves_and_cost_by_product[key]
            if moves_cost is not None:
                product_cost = moves_cost
                source = "moves"
                if cost_currency.is_zero(product_cost) and line.order_id.shipping_date:
                    refunded = line.refunded_orderline_id
                    if refunded and refunded.qty:
                        product_cost = (
                            refunded.price_cost
                            or refunded.currency_id._convert(
                                refunded.total_cost / refunded.qty,
                                cost_currency,
                                refunded.company_id,
                                refunded.order_id.date_order,
                                round=False,
                            )
                        )
                        source = "refunded line"
                    else:
                        product_cost = product.standard_price
                        source = "standard_price (zero move cost)"
            else:
                product_cost = product.standard_price
                source = "standard_price"
            _debug.logic(
                "line_total_cost_source",
                order=line.order_id.uuid,
                line=line.id,
                cost=product_cost,
                source=source,
                moves=moves or None,
            )
            line.write(
                {
                    "total_cost": line.qty
                    * cost_currency._convert(
                        from_amount=product_cost,
                        to_currency=line.currency_id,
                        company=line.company_id or self.env.company,
                        date=line.order_id.date_order or fields.Date.today(),
                        round=False,
                    ),
                    "price_cost": product_cost,
                    "is_total_cost_computed": True,
                }
            )

    def _get_stock_moves_to_consider(self, stock_moves, product):
        self.check_singleton()
        return stock_moves.filtered(lambda ml: ml.product_id.id == product.id)

    @api.depends("price_subtotal", "total_cost")
    def _compute_margins(self) -> None:
        for line in self:
            if line.product_id.type == "combo":
                line.margin = 0
                line.margin_percent = 0
            else:
                line.margin = line.price_subtotal - line.total_cost
                line.margin_percent = (
                    not line.currency_id.is_zero(line.price_subtotal)
                    and line.margin / line.price_subtotal
                ) or 0

    def _prepare_base_line_for_taxes_computation(self):
        self.check_singleton()
        commercial_partner = self.order_id.partner_id.commercial_partner_id
        fiscal_position = self.order_id.fiscal_position_id
        line = self.with_company(self.order_id.company_id)
        account = (
            line.product_id._get_product_accounts()["income"]
            or self.order_id.config_id.journal_id.default_account_id
        )
        if not account:
            raise UserError(
                self.env._(
                    "Please define income account for this product: '%(product)s' (id:%(id)d).",
                    product=line.product_id.name,
                    id=line.product_id.id,
                )
            )

        if fiscal_position:
            account = fiscal_position.map_account(account)

        is_refund_order = line.order_id._is_refund_order()
        is_refund_line = line.qty * line.price_unit < 0

        lang = line.order_id.partner_id.lang or self.env.user.lang
        product_name = (
            line.with_context(lang=lang).full_product_name
            or line.product_id.with_context(lang=lang).display_name
        )
        if line.product_id.description_sale:
            product_name += (
                "\n" + line.product_id.with_context(lang=lang).description_sale
            )
        return {
            **self.env["account.tax"]._prepare_base_line_for_taxes_computation(
                line,
                partner_id=commercial_partner,
                currency_id=self.order_id.currency_id,
                rate=self.order_id.currency_rate,
                product_id=line.product_id,
                tax_ids=line.tax_ids_after_fiscal_position,
                price_unit=line.price_unit,
                quantity=line.qty * (-1 if is_refund_order else 1),
                discount=line.discount,
                account_id=account,
                is_refund=is_refund_line,
                sign=1 if is_refund_order else -1,
            ),
            "uom_id": line.product_uom_id,
            "name": product_name,
        }

    def _prepare_tax_base_line_values(self):
        return [line._prepare_base_line_for_taxes_computation() for line in self]

    def unlink(self):
        _debug.lifecycle("line_unlink", lines=self)
        bodies_per_order = defaultdict(list)
        for line in self:
            if line.order_id.config_id.order_edit_tracking:
                bodies_per_order[line.order_id].append(
                    self.env._(
                        "%(product_name)s: Deleted line (quantity: %(qty)s)",
                        product_name=line.full_product_name,
                        qty=line.qty,
                    )
                )
        for order, bodies in bodies_per_order.items():
            order.has_deleted_line = True
            body = bodies[0] if len(bodies) == 1 else order._markup_list_message(bodies)
            order.message_post(body=order._prepare_pos_log(body))
        return super().unlink()

    def _get_discount_amount(self):
        self.check_singleton()
        original_price = self.tax_ids_after_fiscal_position.compute_all(
            self.price_unit,
            self.currency_id,
            self.qty,
            product=self.product_id,
            partner=self.order_id.partner_id,
        )["total_included"]
        return original_price - self.price_subtotal_incl
