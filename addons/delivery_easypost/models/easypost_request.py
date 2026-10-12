import datetime
import re

from odoo.exceptions import UserError
from odoo.libs.numbers import float_is_zero
from odoo.tools.urls import urljoin as url_join

API_BASE_URL = "https://api.easypost.com/v2/"
NON_BLOCKING_MESSAGES = ["rate_message"]


class EasypostRequest:
    def __init__(self, carrier, api_key, debug_logger) -> None:
        self.carrier = carrier
        self.api_key = api_key
        self.debug_logger = debug_logger
        self.is_domestic_shipping = None

    def _send_api_request(self, endpoint, request_type="get", data=None):
        access_url = url_join(API_BASE_URL, endpoint)
        self.debug_logger(
            "%s\n%s\n%s" % (access_url, request_type, data or None),
            "easypost_request_%s" % endpoint,
        )
        response = self.carrier._get_integration_connection()._egress_request(
            "GET" if request_type == "get" else "POST",
            access_url,
            purpose="easypost",
            auth=(self.api_key, ""),
            data=data,
        )
        self.debug_logger(
            "%s\n%s" % (response.status_code, response.text),
            "easypost_response_%s" % endpoint,
        )
        response = response.json()
        if "error" in response:
            error_message = response["error"].get("message")
            error_detail = response["error"].get("errors")
            if error_detail:
                error_message += "".join(
                    [
                        "\n - %s: %s"
                        % (
                            err.get("field", self.carrier.env._("Unspecified field")),
                            err.get("message", self.carrier.env._("Unknown error")),
                        )
                        for err in error_detail
                    ]
                )
            raise UserError(
                self.carrier.env._("Easypost returned an error: %s", error_message)
            )
        return response

    def get_easypost_carrier(self):
        carriers = self._send_api_request("carrier_accounts")
        carriers = {c["readable"]: c["id"] for c in carriers}
        if carriers:
            return carriers
        else:
            raise UserError(
                self.carrier.env._(
                    "You have no carrier linked to your Easypost Account.\
                Please connect to Easypost, link your account to carriers and then retry."
                )
            )

    def get_easypost_user(self):
        return self._send_api_request("users")

    def _check_required_value(
        self, carrier, recipient, shipper, order=False, picking=False
    ) -> str | tuple | bool:
        if carrier.prod_environment and not carrier.sudo().easypost_production_api_key:
            raise UserError(
                self.carrier.env._(
                    "The %s carrier is missing (Missing field(s) :\n Production API Key)",
                    carrier.name,
                )
            )
        if not carrier.sudo().easypost_test_api_key:
            raise UserError(
                self.carrier.env._(
                    "The %s carrier is missing (Missing field(s) :\n Test API Key)",
                    carrier.name,
                )
            )

        if not carrier.easypost_delivery_type:
            raise UserError(
                self.carrier.env._(
                    "The %s carrier is missing (Missing field(s) :\n Delivery Carrier Type)",
                    carrier.name,
                )
            )

        if not carrier.easypost_default_package_type_id:
            raise UserError(
                self.carrier.env._(
                    "The %s carrier is missing (Missing field(s) :\n Default Package Type)",
                    carrier.name,
                )
            )

        if not order and not picking:
            raise UserError(self.carrier.env._("Sale Order/Stock Picking is missing."))

        if order:
            if not order.line_ids:
                raise UserError(
                    self.carrier.env._("Please provide at least one item to ship.")
                )
            error_lines = order.line_ids._filtered_invalid_delivery_weight()
            if error_lines:
                return self.carrier.env._(
                    "The estimated shipping price cannot be computed because the weight is missing for the following product(s): \n %s",
                    ", ".join(error_lines.product_id.mapped("name")),
                )

        if picking:
            if not picking.move_ids:
                raise UserError(
                    self.carrier.env._("Please provide at least one item to ship.")
                )
            if picking.move_ids.filtered(
                lambda line: not line.weight and line.product_qty != 0
            ):
                raise UserError(
                    self.carrier.env._(
                        "The estimated price cannot be computed because the weight of your product is missing."
                    )
                )
        return True

    def _prepare_address(self, addr_type, addr_obj):
        addr_fields = {
            "street1": "street",
            "street2": "street2",
            "city": "city",
            "zip": "zip",
            "email": "email",
        }
        address = {
            "order[%s][%s]" % (addr_type, field_name): addr_obj[addr_obj_field]
            for field_name, addr_obj_field in addr_fields.items()
            if addr_obj[addr_obj_field]
        }
        if phone := addr_obj.phone_ids._primary().number:
            address["order[%s][phone]" % addr_type] = phone
        address["order[%s][name]" % addr_type] = (
            addr_obj.name or addr_obj.display_name
        )[:25]
        if addr_obj.state_id:
            address["order[%s][state]" % addr_type] = addr_obj.state_id.code
        address["order[%s][country]" % addr_type] = addr_obj.country_id.code
        if addr_obj.commercial_company_name:
            address["order[%s][company]" % addr_type] = (
                addr_obj.commercial_company_name[:25]
            )
        return address

    def _prepare_shipments(self, carrier, packages, is_return=False):
        shipment = {}
        for shp_id, pkg in enumerate(packages):
            shipment.update(
                self._prepare_parcel(
                    carrier, shp_id, pkg, carrier.easypost_label_file_type
                )
            )
            shipment.update(
                self._customs_info(carrier, shp_id, pkg.commodities, pkg.currency_id)
            )
            shipment.update(self._options(shp_id, carrier))
        if is_return:
            shipment.update({"order[is_return]": True})
        return shipment

    def _prepare_parcel(
        self, carrier, shipment_id, delivery_package, label_format="pdf"
    ):
        shipment = {
            "order[shipments][%d][parcel][weight]"
            % shipment_id: carrier._easypost_convert_weight(delivery_package.weight),
            "order[shipments][%d][options][label_format]" % shipment_id: label_format,
            "order[shipments][%d][options][label_date]"
            % shipment_id: datetime.datetime.now().isoformat(),
            "order[shipments][%d][options][print_custom_1]"
            % shipment_id: delivery_package.picking_id.display_name
            if delivery_package.picking_id
            else delivery_package.order_id.display_name,
        }
        packages = carrier._easypost_get_services_and_package_types()[0]
        if delivery_package.packaging_type and any(
            delivery_package.packaging_type in pkg_names
            for pkg_names in packages.values()
        ):
            shipment.update(
                {
                    "order[shipments][%d][parcel][predefined_package]"
                    % shipment_id: delivery_package.packaging_type
                }
            )
        elif all(dim > 0 for dim in delivery_package.dimension.values()):
            shipment.update(
                {
                    "order[shipments][%d][parcel][%s]"
                    % (shipment_id, dim): delivery_package.dimension[dim]
                    for dim in ["height", "width", "length"]
                }
            )
        else:
            raise UserError(
                self.carrier.env._(
                    "Package type used in pack %s is not configured for easypost.",
                    delivery_package.name,
                )
            )
        return shipment

    def _customs_info(self, carrier, shipment_id, commodities, currency):
        if self.is_domestic_shipping:
            return {}

        customs_info = {}
        contents_explanation = ", ".join(
            [
                "%s" % (re.sub(r"[\W_]+", " ", commodity.product_id.name or ""))
                for commodity in commodities
            ]
        )[:255]
        customs_info.update(
            {
                "order[shipments][%d][customs_info][contents_explanation]"
                % (shipment_id): contents_explanation
            }
        )
        for customs_item_id, commodity in enumerate(commodities):
            customs_info.update(
                {
                    "order[shipments][%d][customs_info][customs_items][%d][description]"
                    % (shipment_id, customs_item_id): commodity.product_id.name,
                    "order[shipments][%d][customs_info][customs_items][%d][quantity]"
                    % (shipment_id, customs_item_id): commodity.qty,
                    "order[shipments][%d][customs_info][customs_items][%d][value]"
                    % (shipment_id, customs_item_id): commodity.monetary_value
                    * commodity.qty,
                    "order[shipments][%d][customs_info][customs_items][%d][currency]"
                    % (shipment_id, customs_item_id): currency.name,
                    "order[shipments][%d][customs_info][customs_items][%d][weight]"
                    % (shipment_id, customs_item_id): carrier._easypost_convert_weight(
                        commodity.product_id.weight * commodity.qty
                    ),
                    "order[shipments][%d][customs_info][customs_items][%d][origin_country]"
                    % (shipment_id, customs_item_id): commodity.country_of_origin,
                    "order[shipments][%d][customs_info][customs_items][%d][hs_tariff_number]"
                    % (shipment_id, customs_item_id): commodity.product_id.hs_code,
                }
            )
        return customs_info

    def _options(self, shipment_id, carrier):
        options = {}
        if carrier.easypost_default_service_id:
            service_otpions = (
                carrier.easypost_default_service_id._get_service_specific_options()
            )
            for option_name, option_value in service_otpions.items():
                options[
                    "order[shipments][%d][options][%s]" % (shipment_id, option_name)
                ] = option_value
        return options

    def rate_request(
        self, carrier, recipient, shipper, order=False, picking=False, is_return=False
    ):
        self._check_required_value(
            carrier, recipient, shipper, order=order, picking=picking
        )

        order_payload = {}

        order_payload["order[reference]"] = "odoo"

        order_payload["order[carrier_accounts][id]"] = carrier.easypost_delivery_type_id

        order_payload.update(self._prepare_address("to_address", recipient))
        order_payload.update(self._prepare_address("from_address", shipper))
        if carrier.easypost_default_service_id._require_residential_address():
            order_payload["order[to_address][residential]"] = True

        self.is_domestic_shipping = (
            order_payload["order[from_address][country]"]
            == order_payload["order[to_address][country]"]
        )

        if picking:
            delivery_packages = carrier._get_packages_from_picking(
                picking, carrier.easypost_default_package_type_id
            )
        else:
            delivery_packages = carrier._get_packages_from_order(
                order, carrier.easypost_default_package_type_id
            )
        order_payload.update(
            self._prepare_shipments(carrier, delivery_packages, is_return=is_return)
        )

        insured_amount = 0.0
        if carrier.shipping_insurance:
            for pkg in delivery_packages:
                insured_amount += carrier._easypost_usd_insured_value(
                    pkg.total_cost, pkg.currency_id
                )
        insurance_cost = 0
        if insured_amount:
            insurance_cost = carrier._easypost_usd_estimated_insurance_cost(
                insured_amount
            )

        response = self._send_api_request("orders", "post", data=order_payload)
        error_message = False
        warning_message = False
        rate = False

        if response.get("messages"):
            warning_message = "\n".join(
                [
                    x["carrier"] + ": " + x["type"] + " -- " + x["message"]
                    for x in response["messages"]
                ]
            )
            response.update({"warning_message": warning_message})

        rates = response.get("rates")
        if not rates:
            error_message = self.carrier.env._(
                "It seems Easypost do not provide shipments for this order.\
                We advise you to try with another package type or service level."
            )
        elif rates and not carrier.easypost_default_service_id:
            rate = self._sort_rates(rates)[0]
            carrier._create_services(rates)
        elif rates and carrier.easypost_default_service_id:
            rate = [
                rate
                for rate in rates
                if rate["service"] == carrier.easypost_default_service_id.name
            ]
            if not rate:
                error_message = self.carrier.env._(
                    "There is no rate available for the selected service level for one of your package. Please choose another service level."
                )
            else:
                rate = rate[0]

        if error_message and warning_message:
            error_message += warning_message

        response.update(
            {
                "error_message": error_message,
                "rate": rate,
                "insurance_cost": insurance_cost,
                "insured_amount": insured_amount,
                "shipment_ids": [
                    shipment["id"] for shipment in response.get("shipments", [])
                ],
            }
        )

        return response

    def send_shipping(self, carrier, recipient, shipper, picking, is_return=False):
        result = self.rate_request(
            carrier, recipient, shipper, picking=picking, is_return=is_return
        )
        if result.get("error_message"):
            return result

        buy_order_payload = {}
        buy_order_payload["carrier"] = result["rate"]["carrier"]
        buy_order_payload["service"] = result["rate"]["service"]
        endpoint = "orders/%s/buy" % result["id"]
        response = self._send_api_request(endpoint, "post", data=buy_order_payload)
        response = self._post_process_ship_response(
            response, carrier=carrier, picking=picking
        )
        messages = response.get("messages", [])
        message_type = messages[0].get("type") if messages else None
        message_carrier = messages[0].get("carrier") if messages else None
        if (
            message_type
            and message_type not in NON_BLOCKING_MESSAGES
            and (message_carrier != "LoomisExpress" or message_type != "rate_error")
        ):
            raise UserError(
                "\n".join(
                    [
                        x["carrier"] + ": " + x["type"] + " -- " + x["message"]
                        for x in response["messages"]
                    ]
                )
            )

        result["track_shipments_url"] = {
            res["tracking_code"]: res["tracker"]["public_url"]
            for res in response["shipments"]
            if res["tracker"]
        }
        result["track_label_data"] = {
            res["tracking_code"]: res["postage_label"]["label_url"]
            for res in response["shipments"]
            if res["postage_label"]
        }

        result["forms"] = {
            form["form_type"]: form["form_url"]
            for res in response["shipments"]
            for form in res.get("forms", [])
        }

        for shp_id in result.get("shipment_ids"):
            insured_amount = result.get("insured_amount")
            if not float_is_zero(insured_amount, precision_rounding=2):
                endpoint = "shipments/%s/insure" % shp_id
                response = self._send_api_request(
                    endpoint, "post", data={"amount": insured_amount}
                )
        return result

    def get_tracking_link(self, order_id):
        endpoint = "orders/%s" % order_id
        response = self._send_api_request(endpoint)
        return [
            [shipment["tracking_code"], shipment["tracker"]["public_url"]]
            for shipment in response.get("shipments")
        ]

    def get_tracking_link_from_code(self, code) -> list:
        endpoint = "trackers"
        response = self._send_api_request(endpoint, "get", data={"tracking_code": code})
        return [
            [tracker["tracking_code"], tracker["public_url"]]
            for tracker in response.get("trackers")
        ]

    def _sort_rates(self, rates):
        return sorted(rates, key=lambda rate: float(rate.get("rate")))

    def _post_process_ship_response(self, response, carrier=False, picking=False):
        if (
            response.get("messages")
            and carrier.easypost_delivery_type in ["Purolator", "DPD UK", "UPS"]
            and len(response.get("shipments", [])) > 1
            and len(response.get("shipments")[0].get("rates", [])) > 0
            and all(len(s.get("rates", [])) == 0 for s in response["shipments"][1:])
        ):
            if carrier.easypost_delivery_type == "UPS" and not all(
                s.get("messages") for s in response["shipments"][1:]
            ):
                return response
            if carrier.easypost_delivery_type in ["Purolator", "DPD UK"] and (
                len(response["messages"]) != 1
                or response["messages"][0].get("type", "") != "rate_error"
                or "multi-shipment rate includes this shipment."
                not in response["messages"][0].get("message", "")
            ):
                return response

            if picking:
                picking.message_post(body=response.get("messages"))
            response["messages"] = False
        return response
