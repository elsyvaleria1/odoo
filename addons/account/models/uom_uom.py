from odoo import api, models

UOM_TO_UNECE_CODE = {
    "base.product_uom_unit": "C62",
    "base.product_uom_dozen": "DZN",
    "base.product_uom_kgm": "KGM",
    "base.product_uom_gram": "GRM",
    "base.product_uom_day": "DAY",
    "base.product_uom_hour": "HUR",
    "base.product_uom_minute": "MIN",
    "base.product_uom_ton": "TNE",
    "base.product_uom_meter": "MTR",
    "base.product_uom_km": "KMT",
    "base.product_uom_cm": "CMT",
    "base.product_uom_litre": "LTR",
    "base.product_uom_lb": "LBR",
    "base.product_uom_oz": "ONZ",
    "base.product_uom_inch": "INH",
    "base.product_uom_foot": "FOT",
    "base.product_uom_mile": "SMI",
    "base.product_uom_floz": "OZA",
    "base.product_uom_qt": "QTL",
    "base.product_uom_gal": "GLL",
    "base.product_uom_cubic_meter": "MTQ",
    "base.product_uom_cubic_inch": "INQ",
    "base.product_uom_cubic_foot": "FTQ",
    "uom.uom_square_meter": "MTK",
    "uom.uom_square_foot": "FTK",
    "base.product_uom_yard": "YRD",
    "base.product_uom_millimeter": "MMT",
    "base.product_uom_kwh": "KWH",
}


class UomUom(models.Model):
    _name = "uom.uom"
    _inherit = ["uom.uom", "mixin.fiscal.country.codes"]

    def _get_unece_code(self):
        xml_ids = self._get_external_ids().get(self.id, [])
        matches = list(set(xml_ids) & set(UOM_TO_UNECE_CODE.keys()))
        return (matches and UOM_TO_UNECE_CODE[matches[0]]) or "C62"

    @api.model
    def _get_uom_from_unece_code(self, unece_code):
        unece_code_to_uom = {v: k for k, v in UOM_TO_UNECE_CODE.items()}
        uom_xmlid = unece_code_to_uom.get(unece_code, "base.product_uom_unit")
        return self.env.ref(uom_xmlid, raise_if_not_found=False)
