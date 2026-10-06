import re
from collections import Counter

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProductTrace(models.Model):
    _name = "product.trace"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _description = "Lot/Serial Number"
    _check_company_auto = True
    _order = "name, id"

    name = fields.Char(
        string="Lot/Serial Number",
        compute="_compute_name",
        precompute=True,
        store=True,
        index="trigram",
        readonly=False,
        required=True,
        help="Unique Lot/Serial Number",
    )
    active = fields.Boolean(default=True)
    ref = fields.Char(
        string="Internal Reference",
        help="Internal reference number in case it differs from the manufacturer's lot/serial number",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        index=True,
        required=True,
        domain="[('tracking', '!=', 'none')] +"
        " ([('product_tmpl_id', '=', context['default_product_tmpl_id'])] if context.get('default_product_tmpl_id') else [])",
        check_company=True,
        tracking=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        related="product_id.uom_id",
        string="Unit",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        store=True,
        index=True,
        readonly=False,
    )
    note = fields.Html(string="Description")
    display_complete = fields.Boolean(compute="_compute_display_complete")
    lot_properties = fields.Properties(
        definition="product_id.lot_properties_definition",
        string="Properties",
        copy=True,
    )

    _name_product_company_uniq = models.Constraint(
        "UNIQUE NULLS NOT DISTINCT (name, product_id, company_id)",
        "The combination of lot/serial number and product must be unique within a company.",
    )

    @api.constrains("name", "product_id", "company_id", "active")
    def _check_unique_lot(self) -> None:
        own_pairs = {(trace.product_id.id, trace.name) for trace in self}
        domain = [
            ("product_id", "in", self.product_id.ids),
            ("name", "in", self.mapped("name")),
        ]
        groupby = ["company_id", "product_id", "name"]
        if any(not trace.company_id for trace in self):
            self = self.sudo()
        records = self.with_context(
            skip_preprocess_gs1=True,
            active_test=False,
        )._read_group(domain, groupby, ["__count"])
        cross_lots = {}
        for company, product, name, count in records:
            if not company:
                cross_lots[(product, name)] = count
        duplicate_pairs = set()
        for company, product, name, count in records:
            if (product.id, name) not in own_pairs:
                continue
            duplicates = count
            if company:
                duplicates += cross_lots.get((product, name), 0)
            if duplicates > 1:
                duplicate_pairs.add((product, name))
        if duplicate_pairs:
            raise self._prepare_duplicate_lot_error(duplicate_pairs)

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                count=len(vals_list),
                keys=sorted({key for vals in vals_list for key in vals}),
            )
        self._check_duplicate_lot_keys(
            (
                vals.get("product_id"),
                vals.get("name"),
                vals.get("company_id") or False,
            )
            for vals in vals_list
        )
        return super(
            ProductTrace, self.with_context(mail_create_nosubscribe=True)
        ).create(vals_list)

    @_debug.perf.timed
    def write(self, vals):
        if _debug.lifecycle.enabled:
            _debug.lifecycle("write", traces=self, keys=sorted(vals))
        if any(field in vals for field in ("name", "product_id", "company_id")):
            _debug.logic("write_identity_change")
            self._check_duplicate_lot_keys(
                [
                    (
                        vals.get("product_id", trace.product_id.id),
                        vals.get("name", trace.name),
                        vals.get("company_id", trace.company_id.id) or False,
                    )
                    for trace in self
                ],
                exclude_ids=self.ids,
            )
        return super().write(vals)

    def copy_data(self, default=None):
        default = default or {}
        vals_list = super().copy_data(default=default)
        if "name" not in default:
            for trace, vals in zip(self, vals_list, strict=True):
                vals["name"] = self._get_free_lot_name(
                    trace.company_id,
                    trace.product_id,
                    self.env._("(copy of) %s", trace.name),
                )
        return vals_list

    @api.model
    def default_get(self, fields):
        context = dict(self.env.context)
        context.pop("default_company_id", False)
        return super(ProductTrace, self.with_context(context)).default_get(fields)

    @api.depends("product_id")
    def _compute_name(self):
        for trace in self:
            if not trace.name:
                trace.name = trace._get_new_name()

    @api.depends("product_id.company_id")
    def _compute_company_id(self):
        for trace in self:
            owner = trace.product_id.company_id
            current = trace.company_id
            if owner and current and current != owner and owner in current.parent_ids:
                # The branch below reads `self.env.company` and
                # `self.env.companies`, so it decides by WHO is computing. That
                # is defensible while the lot is being placed and indefensible
                # afterwards. Measured: a product owned by a parent company, a
                # lot created by a user allowed only in the child, gets the
                # child -- and the same row recomputed by a user allowed in
                # both silently moves to the parent. `company_id` drives
                # the company guard's visibility and `check_company` on the lot's
                # quants and move lines, so that move can hide a lot from the
                # people who created it.
                #
                # A lot sitting strictly BELOW its product's owner is exactly
                # what that branch produces, so it is kept rather than
                # re-decided. Every other shape still falls through: no owner
                # clears the lot as before, an unrelated owner re-derives, and
                # an unset company is decided for the first time.
                continue
            if (
                owner
                and owner in self.env.company.parent_ids
                and owner not in self.env.companies
            ):
                trace.company_id = self.env.company
            else:
                trace.company_id = owner

    @api.depends_context("display_complete")
    def _compute_display_complete(self) -> None:
        for trace in self:
            trace.display_complete = bool(
                trace.id or self.env.context.get("display_complete")
            )

    @api.model
    def _prepare_duplicate_lot_error(self, product_name_pairs) -> ValidationError:
        error_message_lines = sorted(
            self.env._(
                " - Product: %(product)s, Lot/Serial Number: %(lot)s",
                product=product.display_name,
                lot=name,
            )
            for product, name in product_name_pairs
        )
        return ValidationError(
            self.env._(
                "The combination of lot/serial number and product must be unique within a company including when no company is defined.\nThe following combinations contain duplicates:\n%(error_lines)s",
                error_lines="\n".join(error_message_lines),
            ),
        )

    @api.model
    def _check_duplicate_lot_keys(self, keys, exclude_ids=None) -> None:
        keys = [key for key in keys if key[0] and key[1]]
        if not keys:
            return
        duplicates = {key for key, count in Counter(keys).items() if count > 1}
        remaining = set(keys) - duplicates
        if remaining:
            domain = [
                ("product_id", "in", [key[0] for key in remaining]),
                ("name", "in", [key[1] for key in remaining]),
            ]
            if exclude_ids:
                domain.append(("id", "not in", list(exclude_ids)))
            groups = (
                self.sudo()
                .with_context(skip_preprocess_gs1=True, active_test=False)
                ._read_group(domain, ["product_id", "name", "company_id"], ["__count"])
            )
            existing = {
                (product.id, name, company.id if company else False)
                for product, name, company, __ in groups
            }
            duplicates |= remaining & existing
        if duplicates:
            products = self.env["product.product"].browse(
                {product_id for product_id, __, __ in duplicates}
            )
            product_by_id = {product.id: product for product in products}
            raise self._prepare_duplicate_lot_error(
                {
                    (product_by_id[product_id], name)
                    for product_id, name, __ in duplicates
                }
            )

    def _get_new_name(self) -> str:
        self.check_singleton()
        if self.product_id.lot_name_format:
            return self._prepare_name()
        return self._get_next_sequence_value(self.product_id)

    @api.model
    def _get_next_sequence_value(self, product) -> str:
        sequence = product.lot_sequence_id
        value = (
            sequence.next_by_id()
            if sequence
            else self.env["ir.sequence"].next_by_code("product.trace")
        )
        _debug.logic(
            "next_sequence_value",
            product=product.id,
            sequence=sequence.id or "product.trace",
            value=value,
        )
        if not value:
            raise UserError(
                self.env._(
                    "No sequence can name a lot for %(product)s. Set a "
                    "Serial/Lot Numbers Sequence on the product, or restore the "
                    "default one.",
                    product=product.display_name,
                ),
            )
        return value

    @api.model
    def _get_lot_name_placeholders(self) -> dict[str, str]:
        return dict(
            self.env["ir.sequence"]._get_pattern_placeholders(),
            ref=r".+?",
        )

    def _prepare_name_format_mapping(self) -> dict:
        self.check_singleton()
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        values = self.env["ir.sequence"]._get_interpolation_mapping(now)
        values["ref"] = self.ref or self._get_next_sequence_value(self.product_id)
        return values

    def _prepare_name(self) -> str:
        self.check_singleton()
        lot_format = self.product_id.lot_name_format
        try:
            return lot_format % self._prepare_name_format_mapping()
        except (ValueError, TypeError, KeyError) as error:
            raise UserError(
                self.env._(
                    "The Lot/Serial Name Format on %(product)s cannot be used: "
                    "%(error)s.\nExpected placeholders are %(placeholders)s.",
                    product=self.product_id.display_name,
                    error=error,
                    placeholders=", ".join(sorted(self._get_lot_name_placeholders())),
                ),
            ) from None

    @api.model
    def prepare_lot_names(self, first_lot, count) -> list[str]:
        caught_initial_number = re.findall(r"\d+", first_lot)
        if not caught_initial_number:
            return self.prepare_lot_names(first_lot + "0", count)
        initial_number = caught_initial_number[-1]
        padding = len(initial_number)
        splitted = re.split(initial_number, first_lot)
        prefix = initial_number.join(splitted[:-1])
        suffix = splitted[-1]
        initial_number = int(initial_number)

        return [
            f"{prefix}{str(initial_number + i).zfill(padding)}{suffix}"
            for i in range(count)
        ]

    @api.model
    def _get_free_lot_name(self, company, product, first_name, batch=100) -> str:
        Trace = self.with_context(active_test=False)
        owned = Domain("product_id", "=", product.id) & (
            Domain("company_id", "=", company.id) | Domain("company_id", "=", False)
        )
        candidates = [first_name]
        rounds = 0
        while True:
            rounds += 1
            taken = set(
                Trace.search(owned & Domain("name", "in", candidates)).mapped("name")
            )
            for candidate in candidates:
                if candidate not in taken:
                    if _debug.logic.enabled and (rounds > 1 or candidate != first_name):
                        _debug.logic(
                            "free_lot_name",
                            taken=first_name,
                            product=product.id,
                            name=candidate,
                            rounds=rounds,
                        )
                    return candidate
            following = self.prepare_lot_names(candidates[-1], batch + 1)
            candidates = following[1:] if following[0] == candidates[-1] else following

    @api.model
    def _prepare_next_lot_vals(self, company, product) -> dict:
        first_name = self.new({"product_id": product.id})._get_new_name()
        return {
            "product_id": product.id,
            "name": self._get_free_lot_name(company, product, first_name),
        }
