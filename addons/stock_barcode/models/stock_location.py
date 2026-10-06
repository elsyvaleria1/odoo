import base64

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockLocation(models.Model):
    _inherit = "stock.location"
    _search_visibility_fields = ()
    _barcode_field = "barcode"

    barcode_img = fields.Binary(compute="_compute_barcode_img")

    @api.depends("barcode")
    def _compute_barcode_img(self) -> None:
        options = {"width": 300, "height": 100, "humanreadable": True}
        for location in self:
            if location.barcode:
                try:
                    barcode = self.env["ir.actions.report"].prepare_barcode(
                        "Code128", location.barcode, **options
                    )
                    location.barcode_img = base64.b64encode(barcode).decode()
                except ValueError:
                    location.barcode_img = False
            else:
                location.barcode_img = False

    @api.model
    def _search(self, domain, *args, **kwargs):
        domain = self.env.company.sudo().barcodes_config_id.nomenclature_id._preprocess_gs1_search_args(
            domain, ["location", "location_dest"]
        )
        return super()._search(domain, *args, **kwargs)

    @api.model
    def _get_fields_stock_barcode(self):
        return ["barcode", "display_name", "name", "parent_path", "usage"]

    def get_counted_quant_data_records(self):
        _debug.perf.count("location_counted_quants", locations=self)
        self.check_singleton()
        return self.quant_ids.get_stock_barcode_counting_data()
