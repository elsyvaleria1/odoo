from odoo import api, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ReportPosInvoice(models.AbstractModel):
    _name = "report.point_of_sale.report_invoice"
    _description = "Point of Sale Invoice Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        orders = self.env["pos.order"].browse(docids)
        orders.check_access("read")
        uninvoiced_orders = orders.filtered(lambda order: not order.account_move)
        _debug.lifecycle(
            "invoice_report_values",
            docids=docids,
            invoices=orders.account_move.ids,
            not_invoiced=uninvoiced_orders.ids,
        )
        if uninvoiced_orders:
            raise UserError(
                self.env._(
                    "No link to an invoice for %s.",
                    ", ".join(uninvoiced_orders.mapped("name")),
                )
            )

        invoices = orders.account_move
        invoices.check_access("read")
        return self.env["report.account.report_invoice"]._get_report_values(
            invoices.ids, data={"report_type": "pdf", **(data or {})}
        )
