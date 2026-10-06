from odoo import api, models


class MixinAccountExternalTax(models.AbstractModel):
    _inherit = "mixin.account.external.tax"

    def _get_avatax_line_addresses(self, partner, warehouse_id) -> dict:
        """Get the line level addresses from the warehouse.

        :param partner: the partner we are shipping to.
        :param warehouse_id: the warehouse that the product is shipped from.
        :return: the AddressesModel to return to Avatax
        :rtype: dict
        """

        # A 'shipTo' parameter must be added to line level addresses too because when 'addresses' is set at the line
        # level, it no longer inherits any addresses from the root document level which means we must set both the
        # 'shipFrom' and 'shipTo' values for that line.
        # More at: https://developer.avalara.com/avatax/dev-guide/customizing-transaction/address-types/
        return {
            "shipFrom": self._get_avatax_address(warehouse_id.partner_id),
            "shipTo": self._get_avatax_address(partner),
        }

    @api.model
    def _prepare_avatax_document_line_service_call(self, line_data, is_refund):
        """Override to set addresses that will contain the originating and destination locations."""
        res = super()._prepare_avatax_document_line_service_call(line_data, is_refund)

        warehouse = line_data["warehouse_id"]
        # If the product is shipped from a different address, add the correct address to the LineItemModel
        if (
            warehouse
            and warehouse.partner_id
            != line_data["base_line"]["record"].company_id.partner_id
        ):
            res["addresses"] = self._get_avatax_line_addresses(
                line_data["shipping_partner"], warehouse
            )

        return res
