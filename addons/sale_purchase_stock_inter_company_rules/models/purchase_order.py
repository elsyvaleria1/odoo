from odoo import Command, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _prepare_sale_order_data(self, name, partner, company, direct_delivery_address):
        res = super()._prepare_sale_order_data(
            name, partner, company, direct_delivery_address
        )
        warehouse = (
            company.intercompany_warehouse_id
            if company.intercompany_warehouse_id.company_id.id == company.id
            else False
        )
        if not warehouse:
            warehouse = self.env["stock.warehouse"].search(
                [("company_id", "=", company.id)], limit=1
            )
        if not warehouse:
            _debug.logic(
                "intercompany_warehouse_unresolved",
                order=self,
                company=company,
                reason="no_warehouse_for_company",
            )
            raise UserError(
                self.env._(
                    "Configure correct warehouse for company(%s) from Menu: Settings/Users/Companies",
                    company.name,
                )
            )
        res["warehouse_id"] = warehouse.id

        picking_type_warehouse_partner_id = (
            self.picking_type_id.warehouse_id.partner_id.id
        )
        _debug.logic(
            "intercompany_sale_order_addresses",
            order=self,
            warehouse=warehouse,
            shipping_from_picking_type=bool(picking_type_warehouse_partner_id),
        )
        if picking_type_warehouse_partner_id:
            res["partner_shipping_id"] = picking_type_warehouse_partner_id

        return res

    def _prepare_sale_order_line_data(self, line, company):
        res = super()._prepare_sale_order_line_data(line, company)
        if line.product_id.sale_delay:
            res["customer_lead"] = (
                line.product_id and line.product_id.sale_delay
            ) or 0.0
        so_lines = (
            self.env["stock.move"]
            .browse(line.move_ids._rollup_move_dest_ids())
            .mapped("sale_line_id")
        )
        so_line = so_lines[0] if so_lines else line.move_dest_ids.sale_line_id
        _debug.logic(
            "intercompany_origin_sale_line",
            line=line,
            sale_line=so_line or None,
            by="rollup" if so_lines else "move_dest",
        )
        res["product_custom_attribute_value_ids"] = [
            Command.create(
                {
                    "custom_product_template_attribute_value_id": pcav.custom_product_template_attribute_value_id.id,
                    "custom_value": pcav.custom_value,
                }
            )
            for pcav in so_line.product_custom_attribute_value_ids
        ]
        return res

    def _get_location_destination_record(self):
        res = super()._get_location_destination_record()

        if self.dest_address_id and (sale_order := self._get_sale_orders()[:1]):
            partner_company = self.env["res.company"]._find_company_from_partner(
                sale_order.partner_id.id
            )
            if (
                partner_company
                and partner_company != self.company_id
                and self.dest_address_id != sale_order.partner_id
            ):
                _debug.logic(
                    "dropship_destination_intercompany_transit",
                    order=self,
                    sale_order=sale_order,
                    partner_company=partner_company,
                )
                return sale_order.partner_id.property_stock_customer
        return res
