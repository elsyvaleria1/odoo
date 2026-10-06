from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockScrap(models.Model):
    _name = "stock.scrap"
    _inherit = ["stock.scrap", "mixin.barcodes.barcode_events"]

    def on_barcode_scanned(self, barcode):
        _debug.pipeline("scrap_barcode_scanned", scraps=self, barcode=barcode)
        self.check_singleton()
        product = self.env["product.product"].search(
            [("barcode", "=", barcode)], limit=1
        )
        if product and self.product_id == product:
            self.scrap_qty += 1
        elif product:
            self.scrap_qty = 1
            self.product_id = product
            self.trace_id = False
        else:
            lot = self._find_lot_from_barcode(barcode)
            if lot and self.trace_id == lot:
                self.scrap_qty += 1
            elif lot:
                self.scrap_qty = 1
                self.trace_id = lot.id
                self.product_id = lot.product_id

    def _find_lot_from_barcode(self, barcode):
        """Return at most one lot named `barcode`.

        A lot name is unique per (product, company) only, so the same name can legitimately
        exist for several products. Searching unbounded and assigning the result to a Many2one
        raises "Expected singleton"; prefer the lot of the product already on the scrap, and
        fall back to any other one.
        """
        _debug.logic("scrap_lot_from_barcode", scraps=self, barcode=barcode)
        Lot = self.env["product.trace"]
        if self.product_id:
            lot = Lot.search(
                [("name", "=", barcode), ("product_id", "=", self.product_id.id)],
                limit=1,
            )
            if lot:
                return lot
        return Lot.search([("name", "=", barcode)], limit=1)
