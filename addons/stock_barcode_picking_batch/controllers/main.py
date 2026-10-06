from odoo import http
from odoo.http import request

from odoo.addons.stock_barcode.controllers.stock_barcode import StockBarcodeController


class StockBarcodePickingBatchController(StockBarcodeController):
    @http.route()
    def main_menu(self, barcode):
        ret_open_batch_picking = self._try_open_batch_picking(barcode)
        if ret_open_batch_picking:
            return ret_open_batch_picking
        return super().main_menu(barcode)

    def _get_barcode_models(self):
        return (*super()._get_barcode_models(), "stock.picking.batch")

    def _try_open_batch_picking(self, barcode):
        batch_picking = request.env["stock.picking.batch"].search(
            [
                ("name", "=", barcode),
            ],
            limit=1,
        )
        if batch_picking:
            action = batch_picking.action_client_action()
            action["context"] = {"active_id": batch_picking.id}
            return {"action": action}
        return False
