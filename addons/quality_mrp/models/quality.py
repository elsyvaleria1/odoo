from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class QualityPoint(models.Model):
    _inherit = "quality.point"

    @api.model
    def _get_domain_for_production(self, quality_points_domain):
        return quality_points_domain

    @api.constrains("measure_on", "picking_type_ids")
    def _check_measure_on(self) -> None:
        for point in self:
            if point.measure_on == "move_line" and any(
                pt.code == "mrp_operation" for pt in point.picking_type_ids
            ):
                raise ValidationError(
                    self.env._(
                        "The Quantity quality check type is not possible with manufacturing operation types."
                    )
                )


class QualityCheck(models.Model):
    _inherit = "quality.check"

    production_id = fields.Many2one(
        comodel_name="mrp.production",
        string="Production Order",
        check_company=True,
    )
    hide_production_id = fields.Boolean(compute="_compute_hide_source_documents")

    def _source_document_fields(self):
        return super()._source_document_fields() + ("production_id",)

    def _on_fail(self):
        super()._on_fail()
        for check in self:
            if (
                check.production_id.product_id.tracking == "serial"
                and check.move_line_id
            ):
                _debug.lifecycle(
                    "check_failed_unpicked",
                    check=check.id,
                    production=check.production_id.id,
                    move=check.move_line_id.move_id.id,
                )
                check.move_line_id.move_id.picked = False

    @api.depends("production_id")
    def _compute_allowed_product_ids(self) -> None:
        for check in self:
            if check.production_id:
                check.allowed_product_ids = (
                    check.production_id.move_finished_ids.product_id
                )
                continue
            super(QualityCheck, check)._compute_allowed_product_ids()

    @api.depends("production_id.qty_producing")
    def _compute_qty_line(self):
        record_without_production = self.env["quality.check"]
        for qc in self:
            if qc.production_id:
                qc.qty_line = qc.production_id.qty_producing
            else:
                record_without_production |= qc
        return super(QualityCheck, record_without_production)._compute_qty_line()

    @api.constrains("product_id", "production_id")
    def _check_allowed_product_ids_with_production(self) -> None:
        for check in self:
            if (
                check.product_id
                and check.production_id
                and check.product_id
                not in check.production_id.move_finished_ids.product_id
            ):
                _debug.logic(
                    "check_refused",
                    reason="product_not_in_production",
                    check=check.id,
                    production=check.production_id.id,
                )
                raise ValidationError(
                    self.env._(
                        "%(product_name)s is not in Production Order %(production_name)s",
                        product_name=check.product_id.name,
                        production_name=check.production_id.name,
                    )
                )

    def _can_move_to_failure_location(self) -> bool:
        self.check_singleton()
        if self.production_id and self.quality_state == "fail":
            return True
        return super()._can_move_to_failure_location()

    def _move_to_failure_location_operation(self, failure_location_id):
        self.check_singleton()
        if self.production_id and failure_location_id:
            _debug.lifecycle(
                "failure_location_set",
                by="operation",
                check=self.id,
                production=self.production_id.id,
                location=failure_location_id,
            )
            self.production_id.move_finished_ids.location_dest_id = failure_location_id
            self.failure_location_id = failure_location_id
        return super()._move_to_failure_location_operation(failure_location_id)

    def _move_to_failure_location_product(self, failure_location_id):
        self.check_singleton()
        if self.production_id and failure_location_id:
            _debug.lifecycle(
                "failure_location_set",
                by="product",
                check=self.id,
                production=self.production_id.id,
                location=failure_location_id,
            )
            self.production_id.move_finished_ids.filtered(
                lambda m: m.product_id == self.product_id
            ).location_dest_id = failure_location_id
        self.failure_location_id = failure_location_id
        return super()._move_to_failure_location_product(failure_location_id)


class QualityAlert(models.Model):
    _inherit = "quality.alert"

    production_id = fields.Many2one(
        comodel_name="mrp.production",
        string="Production Order",
        check_company=True,
    )
