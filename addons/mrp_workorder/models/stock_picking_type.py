from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    prefill_shop_floor_lots = fields.Boolean(
        string="Pre fill lot/serial numbers in shop floor moves ",
        default=False,
        tracking=True,
        help="When enabled, reserved lots for component moves will be displayed in the shop floor. When disabled, lots will always need to be selected manually when processing components in the shop floor.",
    )

    auto_close_production = fields.Boolean(
        string="Close Manufacturing Orders",
        default=True,
        tracking=True,
        help="Allow users to close MO in last work order operation or from the overview tab.",
    )

    def action_mrp_overview(self):
        picking_type_count = self.env["stock.picking.type"].search_count(
            [("code", "=", "mrp_operation")]
        )
        if picking_type_count == 1:
            return self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "mrp_workorder.action_mrp_display"
            )
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "mrp_workorder.mrp_stock_picking_type_action"
        )
        action["domain"] = [("code", "=", "mrp_operation")]
        return action
