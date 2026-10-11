from odoo import models


class ReportPoint_Of_SaleReport_Saledetails(models.AbstractModel):
    _inherit = "report.point_of_sale.report_saledetails"

    def _is_refund_line(self, line) -> bool:
        if line.product_id == line.order_id.config_id.discount_product_id:
            return line.qty * line.price_unit > 0
        return super()._is_refund_line(line)
