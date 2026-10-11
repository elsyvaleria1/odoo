from datetime import timedelta
from typing import Literal, Self

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.numbers import RoundingMethod, float_repr
from odoo.tools import float_compare, float_is_zero, float_round

_RELATIVE_FACTOR_DIGITS = 7


class UomUom(models.Model):
    _name = "uom.uom"
    _description = "Product Unit of Measure"
    _parent_name = "relative_uom_id"
    _parent_store = True
    _order = "sequence, parent_path, id"

    name = fields.Char(
        string="Unit Name",
        translate=True,
        required=True,
    )
    sequence = fields.Integer(
        compute="_compute_sequence",
        precompute=True,
        store=True,
        readonly=False,
    )
    relative_factor = fields.Float(
        string="Contains",
        digits=0,
        default=1.0,
        required=True,
        help="How much bigger or smaller this unit is compared to the reference UoM for this unit",
    )
    rounding = fields.Float(
        string="Rounding Precision",
        compute="_compute_rounding",
    )
    active = fields.Boolean(
        default=True,
        help="Uncheck the active field to disable a unit of measure without deleting it.",
    )
    relative_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Reference Unit",
        index="btree_not_null",
        ondelete="cascade",
    )
    factor = fields.Float(
        string="Absolute Quantity",
        digits=0,
        compute="_compute_factor",
        recursive=True,
        store=True,
    )
    reference_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Dimension",
        compute="_compute_reference_uom_id",
        recursive=True,
        store=True,
        index="btree_not_null",
        help="The root unit this one is ultimately defined against."
        " Two units are convertible if and only if they share it.",
    )
    parent_path = fields.Char(index=True)

    _factor_gt_zero = models.Constraint(
        "CHECK (relative_factor > 0)",
        "The conversion ratio for a unit of measure must be strictly positive!",
    )


    @api.depends("relative_factor")
    def _compute_sequence(self) -> None:
        for uom in self:
            if uom.id:
                continue
            uom.sequence = max(1, min(int(uom.relative_factor * 100.0), 1000))

    def _compute_rounding(self) -> None:
        self.rounding = 10 ** -self._precision_digits()

    @api.depends("relative_factor", "relative_uom_id", "relative_uom_id.factor")
    def _compute_factor(self) -> None:
        for uom in self:
            if uom.relative_uom_id:
                uom.factor = uom.relative_factor * uom.relative_uom_id.factor
            else:
                uom.factor = uom.relative_factor

    @api.depends("relative_uom_id", "relative_uom_id.reference_uom_id")
    def _compute_reference_uom_id(self) -> None:
        for uom in self:
            uom.reference_uom_id = uom.relative_uom_id.reference_uom_id or uom


    @api.onchange("relative_factor", "relative_uom_id")
    def _onchange_critical_fields(self) -> dict | None:
        if self._filter_protected_uoms() and self.create_date < (
            fields.Datetime.now() - timedelta(days=1)
        ):
            return {
                "warning": {
                    "title": self.env._("Warning for %s", self.name),
                    "message": self.env._(
                        "Some critical fields have been modified on %s.\n"
                        "Note that existing data WON'T be updated by this change.\n\n"
                        "As units of measure impact the whole system, this may cause critical issues.\n"
                        "Therefore, changing core units of measure in a running database is not recommended.",
                        self.name,
                    ),
                }
            }
        return None


    @api.constrains("relative_factor", "relative_uom_id")
    def _check_factor(self) -> None:
        for uom in self:
            if (
                not uom.relative_uom_id
                and float_compare(uom.relative_factor, 1.0, precision_digits=12) != 0
            ):
                raise UserError(
                    self.env._(
                        "The unit of measure %s has a conversion ratio but no reference unit."
                        " Either set a reference unit or keep a ratio of 1.",
                        uom.display_name,
                    )
                )


    @api.ondelete(at_uninstall=False)
    def _unlink_except_master_data(self) -> None:
        descendants = self._descendant_uoms()
        locked_uoms = (self | descendants)._filter_protected_uoms()
        if locked_uoms:
            raise UserError(
                self.env._(
                    "The following units of measure are used by the system and cannot be deleted: %s\nYou can archive them instead.",
                    ", ".join(locked_uoms.mapped("name")),
                )
            )
        if descendants:
            raise UserError(
                self.env._(
                    "%(unit)s is the reference unit of %(dependent_units)s."
                    " Deleting it would delete those too. Delete them first, or"
                    " give them another reference unit.",
                    unit=", ".join(self.mapped("name")),
                    dependent_units=", ".join(descendants.mapped("name")),
                )
            )


    def _precision_digits(self) -> int:
        return self.env["decimal.precision"].get_precision("Product Unit")

    def round(self, value: float, rounding_method: RoundingMethod = "HALF-UP") -> float:
        self._check_at_most_one()
        return float_round(
            value,
            precision_digits=self._precision_digits(),
            rounding_method=rounding_method,
        )

    def _check_at_most_one(self) -> None:
        if len(self) > 1:
            self.check_singleton()

    def compare(self, value1: float, value2: float) -> Literal[-1, 0, 1]:
        self._check_at_most_one()
        return float_compare(value1, value2, precision_digits=self._precision_digits())

    def is_zero(self, value: float) -> bool:
        self._check_at_most_one()
        return float_is_zero(value, precision_digits=self._precision_digits())

    @api.depends("name", "relative_factor", "relative_uom_id", "relative_uom_id.name")
    @api.depends_context("formatted_display_name")
    def _compute_display_name(self):
        super()._compute_display_name()
        for uom in self:
            if uom.env.context.get("formatted_display_name") and uom.relative_uom_id:
                factor = (
                    float_repr(uom.relative_factor, _RELATIVE_FACTOR_DIGITS)
                    .rstrip("0")
                    .rstrip(".")
                )
                uom.display_name = (
                    f"{uom.name}\t--{factor or '0'} {uom.relative_uom_id.name}--"
                )

    def _get_quantity_in_unit(
        self,
        qty: float,
        to_unit: Self,
        round: bool = True,
        rounding_method: RoundingMethod = "UP",
        raise_if_failure: bool = True,
    ) -> float:
        if not self or not qty:
            return qty or 0.0
        self.check_singleton()

        if self == to_unit:
            amount = qty
        else:
            if to_unit and not self._has_common_reference(to_unit):
                if raise_if_failure:
                    raise UserError(
                        self.env._(
                            "The unit of measure %(unit)s cannot be converted into %(other_unit)s"
                            " because they do not share a common reference unit.",
                            unit=self.name,
                            other_unit=to_unit.name,
                        )
                    )
                return qty
            amount = qty * self.factor
            if to_unit:
                amount /= to_unit.factor

        if to_unit and round:
            amount = float_round(
                amount,
                precision_rounding=to_unit.rounding,
                rounding_method=rounding_method,
            )

        return amount


    def _get_quantity_lenient(self, qty: float, to_unit: Self, **kwargs) -> float:
        kwargs.pop("raise_if_failure", None)
        return self._get_quantity_in_unit(
            qty, to_unit, raise_if_failure=False, **kwargs
        )

    def _get_quantity_report(self, qty: float, to_unit: Self, **kwargs) -> float:
        return self._get_quantity_lenient(qty, to_unit, **kwargs)

    def _get_quantity_estimate(self, qty: float, to_unit: Self, **kwargs) -> float:
        return self._get_quantity_lenient(qty, to_unit, **kwargs)

    def _get_quantity_reconcile(self, qty: float, to_unit: Self, **kwargs) -> float:
        if self.env.context.get("uom_reconcile_strict"):
            kwargs.pop("raise_if_failure", None)
            return self._get_quantity_in_unit(
                qty, to_unit, raise_if_failure=True, **kwargs
            )
        return self._get_quantity_lenient(qty, to_unit, **kwargs)

    def _conversion_rounding(self, to_unit: Self) -> float:
        self._check_at_most_one()
        if (
            not self
            or not to_unit
            or self == to_unit
            or not self.factor
            or not to_unit.factor
        ):
            return to_unit.rounding if to_unit else self.rounding
        return to_unit.rounding * min(1.0, self.factor / to_unit.factor)

    def _get_quantity_stored(
        self, qty: float, to_unit: Self, rounding_method: RoundingMethod = "HALF-UP"
    ) -> float:
        if not self or not qty or not to_unit or self == to_unit:
            return self._get_quantity_in_unit(
                qty, to_unit, rounding_method=rounding_method
            )
        self.check_singleton()
        amount = self._get_quantity_in_unit(qty, to_unit, round=False)
        return float_round(
            amount,
            precision_rounding=self._conversion_rounding(to_unit),
            rounding_method=rounding_method,
        )

    def _aggregate_rounding(self) -> float:
        self.check_singleton()
        return self.rounding / max(1.0, self.factor)

    def _is_zero_aggregate(self, qty: float) -> bool:
        self._check_at_most_one()
        if not self:
            return float_is_zero(qty, precision_digits=self._precision_digits())
        return float_is_zero(qty, precision_rounding=self._aggregate_rounding())

    def _round_aggregate(self, qty: float) -> float:
        self._check_at_most_one()
        if not self:
            return float_round(qty, precision_digits=self._precision_digits())
        return float_round(qty, precision_rounding=self._aggregate_rounding())

    def _compare_aggregate(self, qty1: float, qty2: float) -> int:
        self._check_at_most_one()
        if not self:
            return float_compare(qty1, qty2, precision_digits=self._precision_digits())
        return float_compare(qty1, qty2, precision_rounding=self._aggregate_rounding())

    def _is_zero_stored(self, qty: float, to_unit: Self) -> bool:
        self._check_at_most_one()
        if not self:
            return to_unit.is_zero(qty)
        return float_is_zero(qty, precision_rounding=self._conversion_rounding(to_unit))

    def _round_to_packaging_multiple(
        self, product_qty: float, uom: Self, rounding_method: RoundingMethod = "HALF-UP"
    ) -> float:
        self.check_singleton()
        if self == uom:
            return product_qty
        packaging_qty = self._get_quantity_in_unit(1, uom, round=False)
        if product_qty and packaging_qty:
            product_qty = (
                float_round(
                    product_qty / packaging_qty,
                    precision_rounding=1.0,
                    rounding_method=rounding_method,
                )
                * packaging_qty
            )
            product_qty = float_round(
                product_qty, precision_rounding=uom.rounding, rounding_method="HALF-UP"
            )
        return product_qty

    def _get_price_in_unit(
        self, price: float, to_unit: Self, raise_if_failure: bool = True
    ) -> float:
        if not self or not price or not to_unit or self == to_unit:
            return price
        self.check_singleton()
        if not self._has_common_reference(to_unit):
            if raise_if_failure:
                raise UserError(
                    self.env._(
                        "A price per %(unit)s cannot be converted into a price per"
                        " %(other_unit)s because they do not share a common"
                        " reference unit.",
                        unit=self.name,
                        other_unit=to_unit.name,
                    )
                )
            return price
        return price * to_unit.factor / self.factor


    def _get_price_lenient(self, price: float, to_unit: Self, **kwargs) -> float:
        kwargs.pop("raise_if_failure", None)
        return self._get_price_in_unit(price, to_unit, raise_if_failure=False, **kwargs)

    def _get_price_report(self, price: float, to_unit: Self, **kwargs) -> float:
        return self._get_price_lenient(price, to_unit, **kwargs)

    def _get_price_estimate(self, price: float, to_unit: Self, **kwargs) -> float:
        return self._get_price_lenient(price, to_unit, **kwargs)

    def _unprotected_uom_xml_ids(self) -> list:
        return [
            "product_uom_hour",
            "product_uom_dozen",
            "product_uom_pack_6",
        ]

    def _filter_protected_uoms(self) -> Self:
        linked_model_data = (
            self.env["ir.model.data"]
            .sudo()
            .search(
                [
                    ("model", "=", self._name),
                    ("res_id", "in", self.ids),
                    ("name", "not in", self._unprotected_uom_xml_ids()),
                ]
            )
        )
        return self.browse(set(linked_model_data.mapped("res_id")))

    def _descendant_uoms(self) -> Self:
        if not self:
            return self
        return (
            self.with_context(active_test=False).search([("id", "child_of", self.ids)])
            - self
        )

    def _get_reference_uom(self) -> Self:
        self.check_singleton()
        return self.reference_uom_id or self

    def _has_common_reference(self, other_uom: Self) -> bool:
        self._check_at_most_one()
        other_uom._check_at_most_one()
        if not self or not other_uom:
            return False
        if self == other_uom:
            return True
        return self._get_reference_uom() == other_uom._get_reference_uom()
