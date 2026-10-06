from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    spreadsheet_template_id = fields.Many2one(
        comodel_name="sale.order.spreadsheet",
        related="template_id.spreadsheet_template_id",
    )
    spreadsheet_ids = fields.One2many(
        comodel_name="sale.order.spreadsheet",
        inverse_name="order_id",
        string="Spreadsheets",
        export_string_translation=False,
    )
    spreadsheet_id = fields.Many2one(
        comodel_name="sale.order.spreadsheet",
        export_string_translation=False,
        compute="_compute_spreadsheet_id",
    )

    @api.onchange("spreadsheet_template_id")
    def _onchange_spreadsheet_template_id(self) -> None:
        self.spreadsheet_id = False

    @api.depends("spreadsheet_ids")
    def _compute_spreadsheet_id(self) -> None:
        for order in self:
            order.spreadsheet_id = order.spreadsheet_ids[:1]

    def action_view_sale_order_spreadsheet(self):
        self.check_singleton()
        if not self.spreadsheet_id:
            _debug.logic(
                "quotation_spreadsheet_instantiated",
                order=self,
                template=self.spreadsheet_template_id,
            )
            self.spreadsheet_template_id.copy({"order_id": self.id})
        return self.spreadsheet_id.action_view_spreadsheet()

    def copy(self, default=None):
        default = dict(default or {})
        sale_orders = super().copy(default=default)
        if "spreadsheet_ids" not in default:
            for order, new_order in zip(self, sale_orders, strict=False):
                # copy the spreadsheet, with all the revisions history
                _debug.pipeline(
                    "quotation_spreadsheets_copied",
                    source=order,
                    target=new_order,
                    spreadsheets=len(order.spreadsheet_ids),
                )
                new_order.spreadsheet_ids = order.spreadsheet_ids.copy(
                    {"order_id": new_order.id}
                )
        return sale_orders

    def write(self, vals):
        if "template_id" in vals:
            orders_changing_template = self.filtered(
                lambda order: (
                    vals["template_id"] != order.template_id.id and order.spreadsheet_id
                )
            )
            _debug.logic(
                "quotation_spreadsheets_dropped",
                reason="template_changed",
                orders=orders_changing_template,
            )
            orders_changing_template.spreadsheet_ids.unlink()
        return super().write(vals)
