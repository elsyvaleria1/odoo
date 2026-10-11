from odoo import models


class UomUom(models.Model):
    _inherit = "uom.uom"

    def _unprotected_uom_xml_ids(self) -> list:
        xml_ids = super()._unprotected_uom_xml_ids()
        return [xml_id for xml_id in xml_ids if xml_id != "product_uom_hour"]
