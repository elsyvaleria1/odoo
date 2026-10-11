from odoo import models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _prepare_purchase_order_data(self, company, company_partner):
        res = super()._prepare_purchase_order_data(company, company_partner)
        warehouse = (
            company.intercompany_warehouse_id
            if company.intercompany_warehouse_id.company_id.id == company.id
            else False
        )
        _debug.logic(
            "intercompany_warehouse_from_company",
            order=self,
            company=company,
            warehouse=warehouse or None,
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
        picking_type_id = company.intercompany_receipt_type_id
        _debug.logic(
            "intercompany_picking_type",
            order=self,
            picking_type=picking_type_id or None,
            by="company_setting" if picking_type_id else "search",
        )
        if not picking_type_id:
            picking_type_id = self.env["stock.picking.type"].search(
                [("code", "=", "incoming"), ("warehouse_id", "=", warehouse.id)],
                limit=1,
            )
        if not picking_type_id:
            _debug.logic(
                "intercompany_picking_type",
                order=self,
                by="intercompany_user_fallback",
                warehouse=warehouse,
            )
            intercompany_uid = company.intercompany_user_id.id
            picking_type_id = (
                self.env["purchase.order"]
                .with_user(intercompany_uid)
                ._get_picking_type(company.id)
            )

        res["picking_type_id"] = picking_type_id.id

        return res


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_location_final(self):
        partner_company = self.env["res.company"]._find_company_from_partner(
            self.order_id.partner_id.id
        )
        if (
            partner_company
            and partner_company != self.company_id
            and self.order_id.partner_id != self.order_id.partner_shipping_id
        ):
            _debug.logic(
                "final_location_intercompany_transit",
                line=self,
                partner_company=partner_company,
                location=self.order_id.partner_id.property_stock_customer,
            )
            return self.order_id.partner_id.property_stock_customer
        return super()._get_location_final()
