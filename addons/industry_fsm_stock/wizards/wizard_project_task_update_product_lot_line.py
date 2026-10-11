from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardProjectTaskUpdateProductLotLine(models.TransientModel):
    _name = "wizard.project.task.update.product.lot.line"
    _description = "Lines for FSM Stock Tracking"

    def _default_warehouse_id(self):
        return [Command.set([self.env.user._get_default_warehouse_id().id])]

    trace_id = fields.Many2one(
        comodel_name="product.trace",
        string="Lot/Serial Number",
        domain="[('product_id', '=', product_id)]",
        check_company=True,
    )
    quantity = fields.Float(
        default=1,
        required=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        export_string_translation=False,
    )
    sale_order_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        export_string_translation=False,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        export_string_translation=False,
    )
    wizard_tracking_line = fields.Many2one(
        comodel_name="wizard.project.task.update.product.lot",
        export_string_translation=False,
    )
    wizard_tracking_line_validated = fields.Many2one(
        comodel_name="wizard.project.task.update.product.lot",
        export_string_translation=False,
    )
    is_same_warehouse = fields.Boolean(
        export_string_translation=False,
        compute="_compute_warehouse",
        default=True,
    )
    warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        export_string_translation=False,
        compute="_compute_warehouse",
        default=lambda self: self._default_warehouse_id(),
    )

    @api.depends_context("uid")
    def _compute_warehouse(self) -> None:
        default_warehouse = self.env.user._get_default_warehouse_id()
        for line in self:
            if line.id:
                so_lines_warehouses = line.sale_order_line_id.move_ids.warehouse_id
                if len(so_lines_warehouses) > 1:
                    line.warehouse_id = so_lines_warehouses.filtered(
                        lambda w: w.id != default_warehouse.id
                    )[0]
                else:
                    line.warehouse_id = so_lines_warehouses or default_warehouse
            else:
                line.warehouse_id = default_warehouse
            line.is_same_warehouse = not line.warehouse_id or (
                line.warehouse_id == default_warehouse
            )
