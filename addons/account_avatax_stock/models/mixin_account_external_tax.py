from odoo import api, models


class MixinAccountExternalTax(models.AbstractModel):
    _inherit = "mixin.account.external.tax"

    def _get_avatax_line_addresses(self, partner, warehouse_id) -> dict:

        return {
            "shipFrom": self._get_avatax_address(warehouse_id.partner_id),
            "shipTo": self._get_avatax_address(partner),
        }

    @api.model
    def _prepare_avatax_document_line_service_call(self, line_data, is_refund):
        res = super()._prepare_avatax_document_line_service_call(line_data, is_refund)

        warehouse = line_data["warehouse_id"]
        if (
            warehouse
            and warehouse.partner_id
            != line_data["base_line"]["record"].company_id.partner_id
        ):
            res["addresses"] = self._get_avatax_line_addresses(
                line_data["shipping_partner"], warehouse
            )

        return res
