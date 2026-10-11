import math

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

from .usps_request import USPSRequest

_debug = DebugLog(__name__)


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("usps", "USPS (Legacy)")],
        ondelete={
            "usps": lambda recs: recs.write(
                {"delivery_type": "fixed", "fixed_price": 0}
            )
        },
    )
    # Fields required to configure
    usps_username = fields.Char(
        string="USPS User ID",
        groups="base.group_system",
    )
    usps_account_validated = fields.Boolean(
        string="Account Validated",
        help="Check this box if your account is validated by USPS",
    )
    usps_delivery_nature = fields.Selection(
        selection=[("domestic", "Domestic"), ("international", "International")],
        string="Delivery Nature",
        default="domestic",
        required=True,
    )
    usps_size_container = fields.Selection(
        selection=[("LARGE", "Large"), ("REGULAR", "Regular")],
        compute="_compute_size_container",
        default="REGULAR",
        store=True,
    )

    @api.depends("usps_container")
    def _compute_size_container(self) -> None:
        for rec in self:
            if rec.usps_container == "VARIABLE":
                rec.usps_size_container = "REGULAR"
            else:
                rec.usps_size_container = "LARGE"

    usps_label_file_type = fields.Selection(
        selection=[("PDF", "PDF"), ("TIF", "TIF")],
        string="USPS (Legacy) Label File Type",
        default="PDF",
    )
    usps_service = fields.Selection(
        selection=[
            ("First Class", "First Class"),
            ("Priority", "Priority"),
            ("Express", "Express"),
        ],
        string="USPS Service",
        default="Express",
        required=True,
    )
    usps_first_class_mail_type = fields.Selection(
        selection=[
            ("LETTER", "Letter"),
            ("FLAT", "Flat"),
            ("PARCEL", "Parcel"),
            ("POSTCARD", "Postcard"),
            ("PACKAGE SERVICE", "Package Service"),
        ],
        string="USPS First Class Mail Type",
        default="LETTER",
    )
    usps_container = fields.Selection(
        selection=[
            ("VARIABLE", "Regular < 12 inch"),
            ("RECTANGULAR", "Rectangular"),
            ("NONRECTANGULAR", "Non-rectangular"),
        ],
        string="Type of container",
        default="VARIABLE",
        required=True,
    )
    usps_domestic_regular_container = fields.Selection(
        selection=[
            ("Flat Rate Envelope", "Flat Rate Envelope"),
            ("Sm Flat Rate Envelope", "Small Flat Rate Envelope"),
            ("Legal Flat Rate Envelope", "Legal Flat Rate Envelope"),
            ("Padded Flat Rate Envelope", "Padded Flat Rate Envelope"),
            ("Flat Rate Box", "Flat Rate Box"),
            ("Sm Flat Rate Box", "Small Flat Rate Box"),
            ("Lg Flat Rate Box", "Large Flat Rate Box"),
            ("Md Flat Rate Box", "Medium Flat Rate Box"),
        ],
        string="Type of USPS domestic regular container",
        default="Lg Flat Rate Box",
    )

    # For international shipping
    usps_international_regular_container = fields.Selection(
        selection=[
            ("FLATRATEENV", "Flat Rate Envelope"),
            ("LEGALFLATRATEENV", "Legal Flat Rate Envelope"),
            ("PADDEDFLATRATEENV", "Padded Flat Rate Envelope"),
            ("FLATRATEBOX", "Flat Rate Box"),
        ],
        string="Type of USPS International regular container",
        default="FLATRATEBOX",
    )
    usps_mail_type = fields.Selection(
        selection=[
            ("Package", "Package"),
            ("Letter", "Letter"),
            ("FlatRate", "Flat Rate"),
            ("FlatRateBox", "Flat Rate Box"),
            ("LargeEnvelope", "Large Envelope"),
        ],
        string="USPS Mail Type",
        default="FlatRateBox",
    )
    usps_content_type = fields.Selection(
        selection=[
            ("SAMPLE", "Sample"),
            ("GIFT", "Gift"),
            ("DOCUMENTS", "Documents"),
            ("RETURN", "Return"),
            ("MERCHANDISE", "Merchandise"),
        ],
        string="Content Type",
        default="MERCHANDISE",
    )
    usps_custom_container_width = fields.Float(string="Package Width")
    usps_custom_container_length = fields.Float(string="Package Length")
    usps_custom_container_height = fields.Float(string="Package Height")
    usps_custom_container_girth = fields.Float(string="Package Girth")
    usps_intl_non_delivery_option = fields.Selection(
        selection=[
            ("RETURN", "Return"),
            ("REDIRECT", "Redirect"),
            ("ABANDON", "Abandon"),
        ],
        string="Non delivery option",
        default="ABANDON",
    )
    usps_redirect_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Redirect Partner",
    )
    usps_machinable = fields.Boolean(
        string="Machinable",
        help="Please check on USPS website to ensure that your package is machinable.",
    )

    @api.depends("usps_delivery_nature")
    def _compute_can_generate_return(self) -> None:
        super()._compute_can_generate_return()
        for carrier in self:
            if carrier.delivery_type == "usps":
                if carrier.usps_delivery_nature == "international":
                    carrier.can_generate_return = False
                else:
                    carrier.can_generate_return = True

    def usps_rate_shipment(self, order) -> dict:
        _debug.pipeline(
            "carrier_rate_request", provider="usps", carrier=self.id, order=order.id
        )
        srm = USPSRequest(self, self.log_xml)

        check_result = srm.check_required_value(
            order.partner_shipping_id,
            self.usps_delivery_nature,
            order.warehouse_id.partner_id,
            order=order,
        )
        if check_result:
            return {
                "success": False,
                "price": 0.0,
                "error_message": check_result,
                "warning_message": False,
            }

        quotes = srm.usps_rate_request(order, self)

        if quotes.get("error_message"):
            return {
                "success": False,
                "price": 0.0,
                "error_message": self.env._("Error:\n%s", quotes["error_message"]),
                "warning_message": False,
            }

        # USPS always returns prices in USD
        if order.currency_id.name == "USD":
            price = quotes["price"]
        else:
            quote_currency = self.env["res.currency"].search(
                [("name", "=", "USD")], limit=1
            )
            price = quote_currency._convert(
                quotes["price"],
                order.currency_id,
                order.company_id,
                order.date_order or fields.Date.today(),
            )

        return {
            "success": True,
            "price": price,
            "error_message": False,
            "warning_message": False,
        }

    def usps_send_shipping(self, pickings):
        _debug.pipeline(
            "carrier_ship_request", provider="usps", carrier=self.id, pickings=pickings
        )
        res = []
        srm = USPSRequest(self, self.log_xml)
        for picking in pickings:
            check_result = srm.check_required_value(
                picking.partner_id,
                self.usps_delivery_nature,
                picking.picking_type_id.warehouse_id.partner_id,
                picking=picking,
            )
            if check_result:
                raise UserError(check_result)

            booking = srm.usps_request(
                picking, self.usps_delivery_nature, self.usps_service, is_return=False
            )

            if booking.get("error_message"):
                raise UserError(booking["error_message"])

            order = picking.sale_id
            company = order.company_id or picking.company_id or self.env.company
            currency_order = picking.sale_id.currency_id
            if not currency_order:
                currency_order = picking.company_id.currency_id

            # USPS always returns prices in USD
            if currency_order.name == "USD":
                price = booking["price"]
            else:
                quote_currency = self.env["res.currency"].search(
                    [("name", "=", "USD")], limit=1
                )
                price = quote_currency._convert(
                    booking["price"],
                    currency_order,
                    company,
                    order.date_order or fields.Date.today(),
                )

            carrier_tracking_ref = booking["tracking_number"]

            logmessage = (
                Markup(
                    self.env._(
                        "Shipment created into USPS <br/> <b>Tracking Number: </b>%s"
                    )
                )
                % carrier_tracking_ref
            )
            usps_labels = [
                (
                    "%s-%s.%s"
                    % (
                        self._get_delivery_label_prefix(),
                        carrier_tracking_ref,
                        self.usps_label_file_type,
                    ),
                    booking["label"],
                )
            ]
            if picking.sale_id:
                for pick in picking.sale_id.picking_ids:
                    pick.message_post(body=logmessage, attachments=usps_labels)
            else:
                picking.message_post(body=logmessage, attachments=usps_labels)

            shipping_data = {
                "exact_price": price,
                "tracking_number": carrier_tracking_ref,
            }
            res.append(shipping_data)
            if self.return_label_on_delivery:
                self.get_return_label(picking)
        return res

    def usps_get_return_label(
        self, picking, tracking_number=None, origin_date=None
    ) -> None:
        srm = USPSRequest(self, self.log_xml)
        check_result = srm.check_required_value(
            picking.partner_id,
            self.usps_delivery_nature,
            picking.picking_type_id.warehouse_id.partner_id,
            picking=picking,
        )
        if check_result:
            raise UserError(check_result)

        booking = srm.usps_request(
            picking, self.usps_delivery_nature, self.usps_service, is_return=True
        )

        if booking.get("error_message"):
            raise UserError(booking["error_message"])

        carrier_tracking_ref = booking["tracking_number"]
        logmessage = (
            self.env._("Shipment created into USPS")
            + Markup("<br/> <b>")
            + self.env._("Tracking Number:")
            + Markup("</b> ")
            + carrier_tracking_ref
        )
        picking.message_post(
            body=logmessage,
            attachments=[
                (
                    "%s-%s-%s.%s"
                    % (
                        self.get_return_label_prefix(),
                        carrier_tracking_ref,
                        1,
                        self.usps_label_file_type,
                    ),
                    booking["label"],
                )
            ],
        )

    def usps_get_tracking_link(self, picking) -> str:
        _debug.logic(
            "carrier_tracking_link",
            provider="usps",
            carrier=self.id,
            picking=picking.id,
        )
        return (
            "https://tools.usps.com/go/TrackConfirmAction_input?qtc_tLabels1=%s"
            % picking.carrier_tracking_ref
        )

    def usps_cancel_shipment(self, picking) -> None:

        _debug.lifecycle(
            "carrier_cancel_request",
            provider="usps",
            carrier=self.id,
            picking=picking.id,
        )
        srm = USPSRequest(self, self.log_xml)

        result = srm.cancel_shipment(picking, self.usps_account_validated)

        if result["error_found"]:
            raise UserError(result["error_message"])
        picking.message_post(
            body=self.env._(
                "Shipment #%s has been cancelled", picking.carrier_tracking_ref
            )
        )
        picking.write({"carrier_tracking_ref": "", "carrier_price": 0.0})

    def _usps_convert_weight(self, weight):
        weight_uom_id = self.env["product.template"]._get_uom_from_setting("weight")
        weight_in_pounds = weight_uom_id._get_quantity_in_unit(
            weight, self.env.ref("base.product_uom_lb")
        )
        pounds = math.floor(weight_in_pounds)
        ounces = round((weight_in_pounds - pounds) * 16, 3)
        # ounces should be at least 1 for the api request not to fail.
        if pounds == 0 and int(ounces) == 0:
            ounces = 1
        return {"pound": pounds, "ounce": ounces}
