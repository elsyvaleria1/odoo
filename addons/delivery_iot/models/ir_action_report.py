import logging

from odoo import models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger(__name__)


_debug = DebugLog(__name__)


class IrActionReport(models.Model):
    _inherit = "ir.actions.report"

    def render_document(self, device_id_list, res_ids, data=None) -> list:
        _debug.pipeline(
            "iot_render_document", reports=self, devices=len(device_id_list)
        )
        if self.report_name not in [
            "delivery_iot.report_shipping_labels",
            "delivery_iot.report_shipping_docs",
        ]:
            return super().render_document(device_id_list, res_ids, data)

        device_ids = self.env["iot.device"].browse(device_id_list)
        if len(device_id_list) != len(device_ids.exists()):
            raise UserError(
                self.env._(
                    "One of the printer used to print the document has been removed.\n"
                    'To reset printers, go to the Inventory App, Configuration tab, "Reset Linked Printers"'
                    " and retry the operation."
                )
            )

        domain = [("res_model", "=", "stock.picking"), ("res_id", "in", res_ids)]
        if self.report_name == "delivery_iot.report_shipping_labels":
            domain = Domain.AND([domain, [("name", "ilike", "Label%")]])
        elif self.report_name == "delivery_iot.report_shipping_docs":
            domain = Domain.AND([domain, [("name", "ilike", "ShippingDoc%")]])

        attachments = self.env["ir.attachment"].search(domain, order="id desc")
        if not attachments:
            _logger.warning(
                "No attachment found for report %s and res_ids %s",
                self.report_name,
                res_ids,
            )
            return []

        return [
            {
                "iotBoxId": device.iot_id.id,
                "deviceId": device.id,
                "deviceIdentifier": device.identifier,
                "deviceName": device.display_name,
                "document": attachment.datas,
            }
            for attachment in attachments
            for device in device_ids
        ]
