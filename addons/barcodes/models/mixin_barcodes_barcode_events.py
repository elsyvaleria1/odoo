from odoo import api, fields, models


class MixinBarcodesBarcode_Events_(models.AbstractModel):
    """Mixin for models that react to a barcode scanned in their form view."""

    _name = "mixin.barcodes.barcode_events"
    _description = "Barcode Event Mixin"

    _barcode_scanned = fields.Char(
        string="Barcode Scanned",
        store=False,
        help="Value of the last barcode scanned.",
    )

    @api.onchange("_barcode_scanned")
    def _on_barcode_scanned(self):
        barcode = self._barcode_scanned
        if barcode:
            self._barcode_scanned = ""
            return self.on_barcode_scanned(barcode)
        return None

    def on_barcode_scanned(self, barcode):
        raise NotImplementedError(
            f"{self._name} inherits mixin.barcodes.barcode_events but does not "
            f"implement on_barcode_scanned()."
        )
