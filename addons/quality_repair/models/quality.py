from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class QualityPoint(models.Model):
    _inherit = "quality.point"

    @api.constrains("measure_on", "picking_type_ids")
    def _check_picking_type_code(self) -> None:
        _debug.logic("quality_repair_picking_type_check", points=self)
        for point in self:
            if point.measure_on == "move_line" and any(
                picking_type.code == "repair_operation"
                for picking_type in point.picking_type_ids
            ):
                raise ValidationError(
                    self.env._(
                        "The Quantity quality check type is not possible with repair operation types."
                    )
                )


class QualityCheck(models.Model):
    _inherit = "quality.check"

    repair_id = fields.Many2one(
        comodel_name="repair.order",
        string="Repair Order",
        index="btree_not_null",
        check_company=True,
    )
    hide_repair_id = fields.Boolean(compute="_compute_hide_source_documents")

    def _source_document_fields(self):
        return super()._source_document_fields() + ("repair_id",)

    @api.depends("repair_id")
    def _compute_allowed_product_ids(self) -> None:
        for check in self:
            if check.repair_id:
                check.allowed_product_ids = check.repair_id.product_id
                continue
            super(QualityCheck, check)._compute_allowed_product_ids()

    @api.constrains("product_id", "repair_id")
    def _check_allowed_product_ids_with_repair(self) -> None:
        _debug.logic("quality_repair_products_check", checks=self)
        for check in self:
            if (
                check.product_id
                and check.repair_id
                and check.product_id != check.repair_id.product_id
            ):
                raise ValidationError(
                    self.env._(
                        "%(product_name)s is not in Repair Order %(repair_name)s",
                        product_name=check.product_id.name,
                        repair_name=check.repair_id.name,
                    )
                )


class QualityAlert(models.Model):
    _inherit = "quality.alert"

    repair_id = fields.Many2one(
        comodel_name="repair.order",
        string="Repair Order",
        index="btree_not_null",
        check_company=True,
    )
