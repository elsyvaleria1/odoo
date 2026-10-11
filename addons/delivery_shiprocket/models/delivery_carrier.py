import logging
from datetime import timedelta

import requests

from odoo import fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps

from .shiprocket_request import ShipRocket

_logger = logging.getLogger(__name__)


_debug = DebugLog(__name__)


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("shiprocket", "Shiprocket")],
        ondelete={
            "shiprocket": lambda recs: recs.write(
                {"delivery_type": "fixed", "fixed_price": 0}
            )
        },
    )
    shiprocket_email = fields.Char(
        help="Enter your Username from Shiprocket account (API)."
    )
    _CREDENTIAL_FIELDS = {
        "shiprocket_password": "password",
        "shiprocket_access_token": "shiprocket_access_token",
    }

    shiprocket_password = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        copy=True,
        classification="secret.credential",
        groups="base.group_system",
        help="Enter your Password from Shiprocket account (API).",
    )
    shiprocket_access_token = fields.Text(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        copy=False,
        help="Generate access token using Shiprocket credentials",
    )

    shiprocket_token_valid_upto = fields.Datetime(
        string="Token Expiry",
        copy=False,
        help="Shiprocket token expires in 10 days. Token will be auto generate based on this token expiry date.",
    )
    shiprocket_channel_id = fields.Many2one(
        comodel_name="shiprocket.channel",
        domain="[('shiprocket_email', '=', shiprocket_email)]",
        help="Get all the integrated channels from your Shiprocket account."
        "This channel id is used to select or specify a custom channel at the time of Shiprocket order creation.",
    )
    shiprocket_courier_ids = fields.Many2many(
        comodel_name="shiprocket.courier",
        string="Shiprocket Couriers",
        copy=False,
        domain="[('shiprocket_email', '=', shiprocket_email)]",
        help="Get all the integrated Couriers from your Shiprocket account."
        "Based on the courier selections the rate will be fetched from the Shiprocket.",
    )
    shiprocket_default_package_type_id = fields.Many2one(
        comodel_name="stock.package.type",
        string="Package Type",
        help="Shiprocket requires package dimensions for getting accurate rate, "
        "you can define these in a package type that you set as default",
    )
    shiprocket_manifests_generate = fields.Boolean(
        string="Generate Manifest",
        help="A manifest is a document that is required by some carriers to streamline the pickup process."
        "particularly when shipping out a high-volume of ecommerce orders.",
    )
    shiprocket_pickup_request = fields.Boolean(
        string="Pickup Request",
        default=True,
        help="Create a pickup request for your order shipment using Validate button of the Delivery Order.",
    )

    def action_shiprocket_test_connection(self) -> dict | None:
        self.check_singleton()
        if self.delivery_type == "shiprocket":
            sr = ShipRocket(self, self.log_xml)
            response_json = sr._authorize_generate_token()
            if response_json.get("token"):
                self.write(
                    {
                        "shiprocket_access_token": response_json["token"],
                        "shiprocket_token_valid_upto": fields.Datetime.now()
                        + timedelta(days=9),
                    }
                )
                message_type = "success"
                message = self.env._("Access token is generated successfully!")
            else:
                if response_json.get("message"):
                    error_message = response_json["message"]
                else:
                    error_message = self.env._(
                        "Authentication failed! Please check your credentials."
                    )
                message_type = "danger"
                message = error_message
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("Shiprocket Notification"),
                    "type": message_type,
                    "message": message,
                    "next": {"type": "ir.actions.act_window_close"},
                },
            }
        return None

    def action_get_channels(self):
        for carrier in self:
            if carrier.delivery_type != "shiprocket":
                continue
            sr = ShipRocket(carrier, self.log_xml)
            channels = sr._get_shiprocket_channels()
            if not channels:
                raise ValidationError(
                    self.env._(
                        "Failed to fetch Shiprocket Channel(s), Please try again later."
                    )
                )
            current_channels = self.env["shiprocket.channel"].search(
                [("shiprocket_email", "=", carrier.shiprocket_email)]
            )
            new_channel_vals = []
            current_channels_by_code = current_channels.grouped("channel_code")
            for name, code in channels.items():
                existing_channels = current_channels_by_code.pop(
                    code, current_channels.browse()
                )
                current_channels -= existing_channels
                if not existing_channels:
                    new_channel_vals.append(
                        {
                            "name": name,
                            "channel_code": code,
                            "shiprocket_email": carrier.shiprocket_email,
                        }
                    )
            if new_channel_vals:
                self.env["shiprocket.channel"].create(new_channel_vals)
            current_channels.unlink()

    def action_get_couriers(self):
        for carrier in self:
            if carrier.delivery_type != "shiprocket":
                continue
            sr = ShipRocket(carrier, self.log_xml)
            couriers_list = sr._get_shiprocket_couriers()
            if not couriers_list:
                raise ValidationError(
                    self.env._(
                        "Failed to fetch Shiprocket Couriers(s), Please try again later."
                    )
                )
            current_couriers = self.env["shiprocket.courier"].search(
                [("shiprocket_email", "=", carrier.shiprocket_email)]
            )
            new_courier_vals = []
            current_couriers_by_code = current_couriers.grouped("courier_code")
            for courier in couriers_list:
                existing_couriers = current_couriers_by_code.pop(
                    courier.get("id"), current_couriers.browse()
                )
                current_couriers -= existing_couriers
                if not existing_couriers:
                    new_courier_vals.append(
                        {
                            "name": courier.get("name"),
                            "courier_code": courier.get("id"),
                            "shiprocket_email": carrier.shiprocket_email,
                        }
                    )
            if new_courier_vals:
                self.env["shiprocket.courier"].create(new_courier_vals)
            current_couriers.unlink()

    def _shiprocket_converted_amount(self, order, price_inr):
        return self.env.ref("base.INR")._convert(
            price_inr,
            order.currency_id,
            order.company_id,
            fields.Date.context_today(self),
        )

    def shiprocket_rate_shipment(self, order) -> dict:
        _debug.pipeline(
            "carrier_rate_request",
            provider="shiprocket",
            carrier=self.id,
            order=order.id,
        )
        sr = ShipRocket(self, self.log_xml)
        result = sr._rate_request(
            order.partner_shipping_id,
            order.warehouse_id.partner_id or order.warehouse_id.company_id.partner_id,
            order,
        )
        if result.get("error_found"):
            return {
                "success": False,
                "price": 0.0,
                "error_message": result["error_found"],
                "warning_message": False,
            }
        price = float(result.get("price"))
        if order.currency_id.id != self.env.ref("base.INR").id:
            price = self._shiprocket_converted_amount(order, price)
        return {
            "success": True,
            "price": price,
            "error_message": False,
            "warning_message": result.get("warning_message"),
        }

    def shiprocket_send_shipping(self, pickings):
        _debug.pipeline(
            "carrier_ship_request",
            provider="shiprocket",
            carrier=self.id,
            pickings=pickings,
        )
        sr = ShipRocket(self, self.log_xml)

        def _get_document_data(url):
            try:
                document_response = self._get_integration_connection()._egress_request(
                    "GET", url, purpose="shiprocket", timeout=30
                )
                document_response.raise_for_status()
                _logger.info("Document downloaded successfully from %s", url)
                return document_response.content
            except requests.exceptions.HTTPError as e:
                _logger.warning("Document download failed from %s - %s", url, e)
            except requests.exceptions.ConnectionError as e:
                _logger.warning("Connection error while downloading %s - %s", url, e)

        res = []
        for picking in pickings:
            shippings = sr._send_shipping(picking)
            picking.shiprocket_orders = " + ".join(shippings.get("order_ids"))
            res.append(
                {
                    "tracking_number": " + ".join(shippings.get("tracking_numbers")),
                    "exact_price": shippings.get("exact_price"),
                }
            )
            for pack in shippings["all_pack"].values():
                response = pack.get("response")
                courier_name = response.get("courier_name")
                carrier_tracking_ref = response.get("awb_code")
                if response.get("warning_message"):
                    picking.message_post(body="%s" % (response["warning_message"]))
                if response.get("label_url"):
                    label_data = _get_document_data(response["label_url"])
                    attachments = [
                        ("%s-%s.pdf" % (courier_name, carrier_tracking_ref), label_data)
                    ]
                    log_message = self.env._(
                        "Label generated for %(courier)s with Tracking Number: %(tracking_ref)s",
                        courier=courier_name,
                        tracking_ref=carrier_tracking_ref,
                    )
                    picking.message_post(body=log_message, attachments=attachments)
                if self.shiprocket_manifests_generate and response.get("manifest_url"):
                    manifest_data = _get_document_data(response["manifest_url"])
                    attachments = [
                        (
                            "Manifest - %s-%s.pdf"
                            % (courier_name, carrier_tracking_ref),
                            manifest_data,
                        )
                    ]
                    log_message = self.env._("Manifest generated of %s", courier_name)
                    picking.message_post(body=log_message, attachments=attachments)
            if not self.prod_environment:
                picking.carrier_tracking_ref = " + ".join(
                    shippings.get("tracking_numbers")
                )
                self.shiprocket_cancel_shipment(picking)
        return res

    def shiprocket_get_tracking_link(self, picking):
        _debug.logic(
            "carrier_tracking_link",
            provider="shiprocket",
            carrier=self.id,
            picking=picking.id,
        )
        tracking_urls = []
        tracking_numbers = (
            picking.carrier_tracking_ref and picking.carrier_tracking_ref.split(" + ")
        ) or []
        for tracking_number in tracking_numbers:
            track_url = (
                str(tracking_number),
                "https://shiprocket.co/tracking/%s" % (tracking_number),
            )
            tracking_urls.append(track_url)
        return (len(tracking_urls) == 1 and tracking_urls[0][1]) or json_dumps(
            tracking_urls
        )

    def shiprocket_cancel_shipment(self, picking):
        _debug.lifecycle(
            "carrier_cancel_request",
            provider="shiprocket",
            carrier=self.id,
            picking=picking.id,
        )
        sr = ShipRocket(self, self.log_xml)
        pickup_request = picking.carrier_id.shiprocket_pickup_request
        shiprocket_orders = []
        if pickup_request:
            if not picking.shiprocket_orders:
                picking.message_post(
                    body=self.env._(
                        "Shiprocket order(s) not found to cancel the shipment!"
                    )
                )
            else:
                shiprocket_orders = picking.shiprocket_orders.split(" + ")
        elif not picking.carrier_tracking_ref:
            picking.message_post(
                body=self.env._("AWB number(s) not found to cancel the shipment!")
            )
        else:
            shiprocket_orders = picking.carrier_tracking_ref.split(" + ")
        if shiprocket_orders:
            cancel_order = sr._send_cancelling(
                shiprocket_orders, pickup_request=pickup_request
            )
            for order, response in cancel_order.items():
                if response.get("status") == 200 or response.get("message"):
                    msg = "Order #" if pickup_request else "AWB #"
                    msg += order + " - " + response.get("message") or self.env._(
                        "Order cancelled successfully!"
                    )
                    picking.message_post(body=msg)
        if not self.prod_environment:
            picking.carrier_tracking_ref = ""
