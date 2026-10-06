import base64
from datetime import UTC, timedelta
from json import JSONDecodeError

from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import loads as json_loads
from odoo.libs.numbers import float_round

from .dhl_request import DHLProvider

HELP_EXTRA_DATA = """Extra data to be sent in the request. It should be JSON-formatted.
This functionality is advanced/technical and should only be used if you know what you are doing.

Example of a valid value: ```
"content": {"packages": {"description": "amazing package"}}
```

With the above example, the description of each package will be updated.
For more information, please refer to the DHL API documentation: https://developer.dhl.com/api-reference/dhl-express-mydhl-api.
"""


_debug = DebugLog(__name__)


class ProviderDHL(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("dhl_rest", "DHL")],
        ondelete={
            "dhl_rest": lambda recs: recs.write(
                {"delivery_type": "fixed", "fixed_price": 0}
            )
        },
    )
    # Doors onto `carrier_credential_id`. A key and a secret map onto the vault's
    # own `api_key` / `api_secret`, so no JSON is needed here.
    _CREDENTIAL_FIELDS = {"dhl_api_key": "api_key", "dhl_api_secret": "api_secret"}

    dhl_api_key = fields.Char(
        string="DHL API Key",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        copy=True,
        classification="secret.credential",
        groups="base.group_system",
    )
    dhl_api_secret = fields.Char(
        string="DHL API Secret",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        copy=True,
        classification="secret.credential",
        groups="base.group_system",
    )

    dhl_account_number = fields.Char(
        string="DHL Account Number",
        groups="base.group_system",
    )
    dhl_unit_system = fields.Selection(
        selection=[("imperial", "Imperial"), ("metric", "Metric")],
        string="Unit System",
        default="metric",
    )
    dhl_default_package_type_id = fields.Many2one(
        comodel_name="stock.package.type",
        string="DHLxw Package Type",
    )
    dhl_region_code = fields.Selection(
        selection=[("AP", "Asia Pacific"), ("AM", "America"), ("EU", "Europe")],
        string="Region",
        default="AM",
    )
    # Nowadays hidden, by default it's the D, couldn't find any documentation on other services
    dhl_product_code = fields.Selection(
        selection=[
            ("0", "0 - Logistics Services"),
            ("1", "1 - Domestic Express 12:00"),
            ("2", "2 - B2C"),
            ("3", "3 - B2C"),
            ("4", "4 - Jetline"),
            ("5", "5 - Sprintline"),
            ("6", "6 - Secureline"),
            ("7", "7 - Express Easy"),
            ("8", "8 - Express Easy"),
            ("9", "9 - Europack"),
            ("A", "A - Auto Reversals"),
            ("B", "B - Break Bulk Express"),
            ("C", "C - Medical Express"),
            ("D", "D - Express Worldwide"),
            ("E", "E - Express 9:00"),
            ("F", "F - Freight Worldwide"),
            ("G", "G - Domestic Economy Select"),
            ("H", "H - Economy Select"),
            ("I", "I - Break Bulk Economy"),
            ("J", "J - Jumbo Box"),
            ("K", "K - Express 9:00"),
            ("L", "L - Express 10:30"),
            ("M", "M - Express 10:30"),
            ("N", "N - Domestic Express"),
            ("O", "O - DOM Express 10:30"),
            ("P", "P - Express Worldwide"),
            ("Q", "Q - Medical Express"),
            ("R", "R - GlobalMail Business"),
            ("S", "S - Same Day"),
            ("T", "T - Express 12:00"),
            ("U", "U - Express Worldwide"),
            ("V", "V - Europack"),
            ("W", "W - Economy Select"),
            ("X", "X - Express Envelope"),
            ("Y", "Y - Express 12:00"),
            ("Z", "Z - Destination Charges"),
        ],
        string="DHL Product",
        default="D",
    )
    dhl_dutiable = fields.Boolean(
        string="Dutiable Material",
        help="Check this if your package is dutiable.",
    )
    dhl_duty_payment = fields.Selection(
        selection=[("S", "Sender"), ("R", "Recipient")],
        default="S",
        required=True,
    )
    dhl_label_image_format = fields.Selection(
        selection=[("EPL2", "EPL2"), ("PDF", "PDF"), ("ZPL2", "ZPL2")],
        string="Label Image Format",
        default="PDF",
    )
    dhl_label_template = fields.Selection(
        selection=[
            ("8X4_A4_PDF", "8X4_A4_PDF"),
            ("8X4_thermal", "8X4_thermal"),
            ("8X4_A4_TC_PDF", "8X4_A4_TC_PDF"),
            ("6X4_thermal", "6X4_thermal"),
            ("6X4_A4_PDF", "6X4_A4_PDF"),
            ("8X4_CI_PDF", "8X4_CI_PDF"),
            ("8X4_CI_thermal", "8X4_CI_thermal"),
            ("8X4_RU_A4_PDF", "8X4_RU_A4_PDF"),
            ("6X4_PDF", "6X4_PDF"),
            ("8X4_PDF", "8X4_PDF"),
        ],
        string="Label Template",
        default="8X4_A4_PDF",
    )
    dhl_extra_data_rate_request = fields.Text(
        string="Extra data for rate requests",
        help=HELP_EXTRA_DATA,
    )
    dhl_extra_data_ship_request = fields.Text(
        string="Extra data for ship requests",
        help=HELP_EXTRA_DATA,
    )
    dhl_extra_data_return_request = fields.Text(
        string="Extra data for return requests",
        help=HELP_EXTRA_DATA,
    )

    def _compute_can_generate_return(self) -> None:
        super()._compute_can_generate_return()
        for carrier in self:
            if carrier.delivery_type == "dhl_rest":
                carrier.can_generate_return = True

    def _compute_supports_shipping_insurance(self):
        super()._compute_supports_shipping_insurance()
        for carrier in self:
            if carrier.delivery_type == "dhl_rest":
                carrier.supports_shipping_insurance = True

    def dhl_rest_rate_shipment(self, order):
        _debug.pipeline(
            "carrier_rate_request", provider="dhl_rest", carrier=self.id, order=order.id
        )
        return self._rate_shipment_vals(order=order)

    def _prepare_dhl_rest_packages_from_order(self, order) -> list:
        self.check_singleton()
        total_weight = order._get_estimated_weight()
        total_weight = self._dhl_rest_convert_weight(total_weight)
        if not total_weight:
            weight_uom_name = self.env[
                "product.template"
            ]._get_weight_uom_name_from_ir_config_parameter()
            raise UserError(
                self.env._(
                    "The package cannot be created because the total weight of the products in the picking is 0.0 %s",
                    weight_uom_name,
                )
            )

        max_weight = self.dhl_default_package_type_id.max_weight or total_weight + 1
        number_of_packages = int(total_weight / max_weight)
        last_package_weight = total_weight % max_weight

        weights = [max_weight] * number_of_packages + (
            [last_package_weight] if last_package_weight else []
        )
        return [
            {
                "weight": weight,
                "dimension": {
                    "length": self.dhl_default_package_type_id.packaging_length,
                    "width": self.dhl_default_package_type_id.width,
                    "height": self.dhl_default_package_type_id.height,
                },
            }
            for weight in weights
        ]

    def _prepare_dhl_rest_packages_from_picking(self, picking):
        self.check_singleton()
        packages = []

        if picking.is_return_picking:
            commodities = self._prepare_commodity_values_from_move_lines(
                picking.move_line_ids
            )
            weight = picking._get_estimated_weight()
            packages.append(
                {
                    "commodities": commodities,
                    "weight": weight,
                    "dimension": {
                        "length": self.dhl_default_package_type_id.packaging_length,
                        "width": self.dhl_default_package_type_id.width,
                        "height": self.dhl_default_package_type_id.height,
                    },
                }
            )
            return packages

        # Create all packages.
        move_lines_by_package = picking.move_line_ids.grouped("result_package_id")
        for package in picking.move_line_ids.result_package_id:
            move_lines = move_lines_by_package[package]
            commodities = self._prepare_commodity_values_from_move_lines(move_lines)
            packages.append(
                {
                    "commodities": commodities,
                    "weight": package.shipping_weight or package.weight,
                    "dimension": {
                        "length": package.package_type_id.packaging_length,
                        "width": package.package_type_id.width,
                        "height": package.package_type_id.height,
                    },
                    "name": package.name,
                }
            )

        # Create one package: either everything is in pack or nothing is.
        if picking.weight_bulk:
            commodities = self._prepare_commodity_values_from_move_lines(
                picking.move_line_ids
            )
            packages.append(
                {
                    "commodities": commodities,
                    "weight": picking.weight_bulk,
                    "dimension": {
                        "length": self.dhl_default_package_type_id.packaging_length,
                        "width": self.dhl_default_package_type_id.width,
                        "height": self.dhl_default_package_type_id.height,
                    },
                    "name": "Bulk Content",
                }
            )
        elif not packages:
            raise UserError(
                self.env._(
                    "The package cannot be created because the total weight of the "
                    "products in the picking is 0.0 %s",
                    picking.weight_uom_name,
                )
            )
        return packages

    def _datetime_to_dhl_utc_string(self, datetime_object):
        """Format a datetime in UTC using DHL's literal ``GMT+00:00`` suffix.

        Naive inputs retain ``datetime.astimezone``'s local-time interpretation.

        :param datetime datetime_object: planned shipping time
        :rtype: str
        """
        return datetime_object.astimezone(tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%S GMT+00:00"
        )

    def _get_dhl_label_format(self) -> str | None:
        match self.dhl_label_image_format:
            case "ZPL2":
                return "zpl"
            case "EPL2":
                return "epl"
            case _:
                return "pdf"

    def _rate_shipment_vals(self, order=False, picking=False) -> dict | None:
        if picking:
            warehouse_partner_id = picking.picking_type_id.warehouse_id.partner_id
            currency_id = picking.sale_id.currency_id or picking.company_id.currency_id
            destination_partner_id = picking.partner_id
            total_value = sum(sml.sale_price for sml in picking.move_line_ids)
            planned_date = picking.date_planned + timedelta(hours=1)
        else:
            warehouse_partner_id = order.warehouse_id.partner_id
            currency_id = order.currency_id or order.company_id.currency_id
            total_value = sum(
                line.price_total
                for line in order.line_ids.filtered(
                    lambda l: (
                        l.product_id.type in ("consu", "product") and not l.display_type
                    )
                )
            )
            destination_partner_id = order.partner_shipping_id
            if hasattr(order, "website_id") and order.website_id:
                planned_date = fields.Datetime.now() + timedelta(hours=1)
            else:
                planned_date = order.date_order + timedelta(hours=1)

        rating_request = {}
        account_number = self.sudo().dhl_account_number
        srm = DHLProvider(self)
        check_value = srm._get_shipping_validation_error(
            self,
            destination_partner_id,
            warehouse_partner_id,
            order=order,
            picking=picking,
        )
        if check_value:
            return {
                "success": False,
                "price": 0.0,
                "error_message": check_value,
                "warning_message": False,
            }
        rating_request["customerDetails"] = {
            "shipperDetails": srm._prepare_shipper_address(warehouse_partner_id),
            "receiverDetails": srm._prepare_recipient_address(destination_partner_id),
        }
        if picking:
            packages = self._prepare_dhl_rest_packages_from_picking(picking)
        else:
            packages = self._prepare_dhl_rest_packages_from_order(order)
        rating_request["packages"] = srm._prepare_package_vals(self, packages)
        rating_request["isCustomsDeclarable"] = self.dhl_dutiable
        if self.dhl_dutiable:
            rating_request["monetaryAmount"] = srm._prepare_dutiable_vals(
                total_value, currency_id.name
            )
        rating_request["unitOfMeasurement"] = self.dhl_unit_system
        if planned_date <= fields.Datetime.now():
            raise UserError(
                self.env._("The planned date for the shipment must be in the future.")
            )
        rating_request["plannedShippingDateAndTime"] = self._datetime_to_dhl_utc_string(
            planned_date
        )
        rating_request["accounts"] = srm._prepare_billing_vals(
            account_number, "shipper"
        )
        self._update_dhl_rest_request_extra_data(rating_request, "rate")
        rating_request["productsAndServices"] = [
            {
                "productCode": self.dhl_product_code,
                "valueAddedServices": [],
            }
        ]
        if self.supports_shipping_insurance and self.shipping_insurance:
            rating_request["productsAndServices"][0]["valueAddedServices"].append(
                srm._prepare_insurance_vals(
                    self.shipping_insurance, total_value, currency_id.name
                )
            )

        response = srm._get_rates(rating_request)

        available_product_code = []
        shipping_charge = False
        products = response["products"]
        for product in products:
            charge = [
                price
                for price in product["totalPrice"]
                if price["currencyType"] == "BILLC"
            ]  # get the price in the billing currency
            global_product_code = product["productCode"]
            if global_product_code == self.dhl_product_code and charge:
                shipping_charge = charge[0]["price"]
                shipping_currency = charge[0]["priceCurrency"]
                break
            available_product_code.append(global_product_code)
        if shipping_charge:
            if order:
                order_currency = order.currency_id
            else:
                order_currency = (
                    picking.sale_id.currency_id or picking.company_id.currency_id
                )
            if shipping_currency is None or order_currency.name == shipping_currency:
                price = float(shipping_charge)
            else:
                quote_currency = self.env["res.currency"].search(
                    [("name", "=", shipping_currency)], limit=1
                )
                price = quote_currency._convert(
                    float(shipping_charge),
                    order_currency,
                    (order or picking).company_id,
                    order.date_order if order else fields.Date.today(),
                )
            if self.supports_shipping_insurance and self.shipping_insurance:
                for product in products:
                    services = []
                    for price_breakdown in product["detailedPriceBreakdown"]:
                        services.extend(
                            [
                                service["serviceCode"]
                                for service in price_breakdown["breakdown"]
                                if "serviceCode" in service
                            ]
                        )
                    if "II" not in services:
                        return {
                            "success": False,
                            "price": 0.0,
                            "error_message": self.env._(
                                "Shipment insurance is not available between the origin and destination. You should try with another DHL product, or select a delivery method with no insurance."
                            ),
                            "warning_message": False,
                        }

            return {
                "success": True,
                "price": price,
                "error_message": False,
                "warning_message": False,
            }

        if available_product_code:
            return {
                "success": False,
                "price": 0.0,
                "error_message": self.env._(
                    "There is no price available for this shipping, you should rather try with the DHL product %s",
                    available_product_code[0],
                ),
                "warning_message": False,
            }
        return None

    def dhl_rest_send_shipping(self, pickings):
        _debug.pipeline(
            "carrier_ship_request",
            provider="dhl_rest",
            carrier=self.id,
            pickings=pickings,
        )
        res = []
        for picking in pickings:
            shipment_request = {}
            srm = DHLProvider(self)
            account_number = self.sudo().dhl_account_number
            planned_date = picking.date_planned
            if planned_date <= fields.Datetime.now():
                raise UserError(
                    self.env._(
                        "The planned date for the shipment must be in the future."
                    )
                )
            shipment_request["plannedShippingDateAndTime"] = (
                self._datetime_to_dhl_utc_string(planned_date)
            )
            shipment_request["pickup"] = {"isRequested": True}
            shipment_request["accounts"] = srm._prepare_billing_vals(
                account_number, "shipper"
            )
            shipment_request["customerDetails"] = {}
            shipment_request["customerDetails"]["receiverDetails"] = (
                srm._prepare_consignee_vals(picking.partner_id)
            )
            shipment_request["customerDetails"]["shipperDetails"] = (
                srm._prepare_shipper_vals(
                    picking.company_id.partner_id,
                    picking.picking_type_id.warehouse_id.partner_id,
                )
            )
            shipment_request["productCode"] = self.dhl_product_code
            shipment_request["customerReferences"] = [
                {
                    "value": picking.sale_id.name if picking.sale_id else picking.name,
                    "typeCode": "CU",
                }
            ]
            shipment_request["content"] = {}
            shipment_request["content"]["description"] = (
                picking.sale_id.name if picking.sale_id else picking.name
            )
            shipment_request["content"]["unitOfMeasurement"] = self.dhl_unit_system
            incoterm = (
                picking.sale_id.incoterm_id
                or self.env.company.account_config_id.incoterm_id
            )
            shipment_request["content"]["incoterm"] = incoterm.code or "EXW"
            total_value, currency_name = self._get_dhl_declared_value_and_currency(
                picking
            )
            shipment_request["content"]["isCustomsDeclarable"] = self.dhl_dutiable
            if self.dhl_dutiable:
                shipment_request["content"]["declaredValue"] = total_value
                shipment_request["content"]["declaredValueCurrency"] = currency_name
            if picking._is_commercial_invoice_required():
                shipment_request["content"]["exportDeclaration"] = (
                    srm._prepare_export_declaration_vals(self, picking)
                )
                shipment_request["content"]["declaredValueCurrency"] = currency_name
            shipment_request["content"]["packages"] = srm._prepare_shipment_vals(
                picking
            )
            shipment_request["outputImageProperties"] = {
                "encodingFormat": self._get_dhl_label_format(),
            }
            shipment_request["outputImageProperties"]["imageOptions"] = [
                {
                    "typeCode": "label",
                    "templateName": self.dhl_label_template,
                }
            ]
            if self.supports_shipping_insurance and self.shipping_insurance:
                shipment_request["valueAddedServices"] = [
                    srm._prepare_insurance_vals(
                        self.shipping_insurance, total_value, currency_name
                    )
                ]
            self._update_dhl_rest_request_extra_data(shipment_request, "ship")
            dhl_response = srm._send_shipment(shipment_request)
            tracking_number = dhl_response["shipmentTrackingNumber"]
            logmessage = Markup("%s<br/><b>%s:</b> %s") % (
                self.env._("Shipment created into DHL"),
                self.env._("Tracking Number"),
                tracking_number,
            )
            dhl_labels = [
                (
                    "LabelShipping-DHL-{}.{}".format(
                        tracking_number, document["imageFormat"]
                    ),
                    base64.b64decode(document["content"]),
                )
                for document in dhl_response["documents"]
                if document["typeCode"] == "label"
            ]
            other_documents = [
                (
                    "ShippingDoc-DHL-{}.{}".format(
                        document["packageReferenceNumber"], document["imageFormat"]
                    ),
                    base64.b64decode(document["content"]),
                )
                for document in dhl_response["documents"]
                if document["typeCode"] != "label"
            ]
            lognote_pickings = (
                picking.sale_id.picking_ids if picking.sale_id else picking
            )
            for pick in lognote_pickings:
                pick.message_post(body=logmessage, attachments=dhl_labels)
                if other_documents:
                    pick.message_post(
                        body=self.env._("DHL Documents"), attachments=other_documents
                    )
            shipping_data = {
                "exact_price": 0,
                "tracking_number": tracking_number,
            }
            rate = self._rate_shipment_vals(picking=picking)
            shipping_data["exact_price"] = rate["price"]
            if self.return_label_on_delivery:
                self.get_return_label(picking)
            res += [shipping_data]

        return res

    def dhl_rest_get_return_label(
        self, picking, tracking_number=None, origin_date=None
    ) -> dict:
        shipment_request = {}
        srm = DHLProvider(self)
        account_number = self.sudo().dhl_account_number
        planned_date = picking.date_planned
        if planned_date <= fields.Datetime.now():
            raise UserError(
                self.env._("The planned date for the shipment must be in the future.")
            )
        shipment_request["plannedShippingDateAndTime"] = (
            self._datetime_to_dhl_utc_string(planned_date)
        )
        shipment_request["pickup"] = {"isRequested": False}
        shipment_request["accounts"] = srm._prepare_billing_vals(
            account_number, "shipper"
        )
        shipment_request["customerDetails"] = {
            "shipperDetails": srm._prepare_shipper_vals(
                picking.partner_id, picking.partner_id
            ),
            "receiverDetails": srm._prepare_consignee_vals(
                picking.picking_type_id.warehouse_id.partner_id
            ),
        }
        shipment_request["productCode"] = self.dhl_product_code
        shipment_request["content"] = {
            "description": picking.sale_id.name if picking.sale_id else picking.name,
            "unitOfMeasurement": self.dhl_unit_system,
            "incoterm": (
                picking.sale_id.incoterm_id
                or self.env.company.account_config_id.incoterm_id
            ).code
            or "EXW",
            "isCustomsDeclarable": self.dhl_dutiable,
            "packages": srm._prepare_shipment_vals(picking),
        }
        total_value, currency_name = self._get_dhl_declared_value_and_currency(picking)
        if self.dhl_dutiable:
            shipment_request["content"]["declaredValue"] = total_value
            shipment_request["content"]["declaredValueCurrency"] = currency_name
        if picking._is_commercial_invoice_required():
            shipment_request["content"]["exportDeclaration"] = (
                srm._prepare_export_declaration_vals(self, picking)
            )
            shipment_request["content"]["declaredValueCurrency"] = currency_name
        shipment_request["outputImageProperties"] = {
            "imageOptions": [
                {
                    "typeCode": "label",
                    "templateName": self.dhl_label_template,
                }
            ]
        }
        shipment_request["valueAddedServices"] = [{"serviceCode": "PV"}]
        self._update_dhl_rest_request_extra_data(shipment_request, "return")
        dhl_response = srm._send_shipment(shipment_request)
        tracking_number = dhl_response["shipmentTrackingNumber"]
        logmessage = Markup("%s<br/><b>%s:</b> %s") % (
            self.env._("Shipment created into DHL"),
            self.env._("Tracking Number"),
            tracking_number,
        )
        dhl_labels = [
            (
                "LabelReturn-DHL-{}.{}".format(
                    tracking_number, document["imageFormat"]
                ),
                base64.b64decode(document["content"]),
            )
            for document in dhl_response["documents"]
            if document["typeCode"] == "label"
        ]
        other_documents = [
            (
                "ShippingDoc-DHL-{}.{}".format(
                    document["packageReferenceNumber"], document["imageFormat"]
                ),
                base64.b64decode(document["content"]),
            )
            for document in dhl_response["documents"]
            if document["typeCode"] != "label"
        ]
        lognote_pickings = picking.sale_id.picking_ids if picking.sale_id else picking
        for pick in lognote_pickings:
            pick.message_post(body=logmessage, attachments=dhl_labels)
            if other_documents:
                pick.message_post(
                    body=self.env._("DHL Documents"), attachments=other_documents
                )
        return {
            "exact_price": 0,
            "tracking_number": tracking_number,
        }

    def dhl_rest_get_tracking_link(self, picking) -> str:
        _debug.logic(
            "carrier_tracking_link",
            provider="dhl_rest",
            carrier=self.id,
            picking=picking.id,
        )
        return f"http://www.dhl.com/en/express/tracking.html?AWB={picking.carrier_tracking_ref}"

    def dhl_rest_cancel_shipment(self, picking) -> None:
        # Obviously you need a pick up date to delete SHIPMENT by DHL. So you can't do it if you didn't schedule a pick-up.
        _debug.lifecycle(
            "carrier_cancel_request",
            provider="dhl_rest",
            carrier=self.id,
            picking=picking.id,
        )
        picking.message_post(
            body=self.env._("You can't cancel DHL shipping without pickup date.")
        )
        picking.write({"carrier_tracking_ref": "", "carrier_price": 0.0})

    def _dhl_rest_convert_weight(self, weight):
        weight_uom_id = self.env[
            "product.template"
        ]._get_weight_uom_id_from_ir_config_parameter()
        unit = self.dhl_unit_system
        if unit == "imperial":
            weight = weight_uom_id._get_quantity_in_unit(
                weight, self.env.ref("uom.product_uom_lb"), round=False
            )
        else:
            weight = weight_uom_id._get_quantity_in_unit(
                weight, self.env.ref("uom.product_uom_kgm"), round=False
            )
        return float_round(weight, 3)

    def _get_dhl_declared_value_and_currency(self, picking) -> tuple:
        """Return the declared amount and currency code for a picking.

        Sale orders contribute non-display product/consumable lines, including
        tax. Without a sale order, use move quantities at product list prices
        and the picking company's currency.

        :param picking: singleton ``stock.picking`` record
        :rtype: tuple[float, str]
        """
        sale_order = picking.sale_id
        if sale_order:
            total_value = sum(
                line.price_total
                for line in sale_order.line_ids
                if not line.display_type
                if line.product_id.type in ["product", "consu"]
            )
            currency_name = picking.sale_id.currency_id.name
        else:
            total_value = sum(
                line.product_id.lst_price * line.product_qty
                for line in picking.move_ids
            )
            currency_name = picking.company_id.currency_id.name
        return total_value, currency_name

    def _update_dhl_rest_request_extra_data(self, request, request_type) -> None:
        """Adds the extra data to the request.
        When there are multiple items in a list, they will all be affected by
        the change.
        for example, with
        {"content": {"packages": {"description": "amazon package"}}}
        the description of each piece will be updated."""
        extra_data_input = {
            "rate": self.dhl_extra_data_rate_request,
            "ship": self.dhl_extra_data_ship_request,
            "return": self.dhl_extra_data_return_request,
        }.get(request_type) or ""
        try:
            extra_data = json_loads("{" + extra_data_input + "}")
        except JSONDecodeError as error:
            raise UserError(self.env._("Invalid syntax for DHL extra data.")) from error

        def extra_data_to_request(request, extra_data):
            """recursive function that adds extra data to the current request"""
            for key, new_value in extra_data.items():
                current_value = request.get(key)
                if isinstance(current_value, list):
                    for item in current_value:
                        extra_data_to_request(item, new_value)
                elif isinstance(new_value, dict) and isinstance(current_value, dict):
                    extra_data_to_request(current_value, new_value)
                else:
                    request[key] = new_value

        extra_data_to_request(request, extra_data)
