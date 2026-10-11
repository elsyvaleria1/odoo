import logging
import math
import re
from typing import Any

from odoo import fields
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero, float_repr, format_list
from odoo.tools.urls import urljoin as url_join

_logger = logging.getLogger(__name__)

BASE_URL = "https://panel.sendcloud.sc/api/v2/"
MULTICOLLO_MAX_PACKAGE = 20


class SendCloud:
    def __init__(self, carrier, public_key, private_key, logger) -> None:
        self.env = carrier.env
        self.logger = logger
        self.session = carrier._get_integration_connection()._egress_session(
            "sendcloud"
        )
        self.session.auth = (public_key, private_key)

    def _get_shipping_functionalities(self):
        return self._send_request("shipping-functionalities")

    def _get_shipping_products(
        self,
        from_country,
        is_return=False,
        carrier=None,
        weight=None,
        to_country=None,
        sizes=None,
        size_unit="centimeter",
        from_postal_code=None,
        to_postal_code=None,
    ):
        params = {"from_country": from_country, "returns": is_return}
        if carrier:
            params.update({"carrier": carrier})
        if to_country:
            params.update({"to_country": to_country})
        if weight:
            params.update({"weight": weight, "weight_unit": "gram"})
        if sizes:
            params.update(
                {
                    "length": sizes.get("length", 0),
                    "height": sizes.get("height", 0),
                    "width": sizes.get("width", 0),
                    "length_unit": size_unit,
                    "height_unit": size_unit,
                    "width_unit": size_unit,
                }
            )
        if from_postal_code or to_postal_code:
            params.update(
                {
                    "from_postal_code": from_postal_code,
                    "to_postal_code": to_postal_code,
                }
            )
        return self._send_request("shipping-products", params=params)

    def _get_shipping_rate(
        self, carrier, order=None, picking=None, parcel=None, order_weight=None
    ) -> tuple | None:
        if order:
            to_country = order.partner_shipping_id.country_id.code
            from_country = order.warehouse_id.partner_id.country_id.code
            to_postal_code = order.partner_shipping_id.zip
            from_postal_code = order.warehouse_id.partner_id.zip
            error_lines = order.line_ids._filtered_invalid_delivery_weight()
            if error_lines:
                raise UserError(
                    self.env._(
                        "The estimated shipping price cannot be computed because the weight is missing for the following product(s): \n %s",
                        ", ".join(error_lines.product_id.mapped("name")),
                    )
                )
            packages = carrier._get_packages_from_order(
                order, carrier.sendcloud_default_package_type_id
            )
            total_weight = order_weight or sum(pack.weight for pack in packages)
        elif picking:
            to_country = picking.destination_country_code
            from_country = picking.location_id.warehouse_id.partner_id.country_id.code
            to_postal_code = picking.partner_id.zip
            from_postal_code = picking.location_id.warehouse_id.partner_id.zip
            total_weight = float(parcel["weight"])
        else:
            raise UserError(self.env._("No picking or order provided"))
        if not to_country or not from_country:
            raise UserError(
                self.env._(
                    "Make sure country codes are set in partner country and warehouse country"
                )
            )
        total_weight = int(carrier.sendcloud_convert_weight(total_weight, grams=True))
        if total_weight < carrier.sendcloud_shipping_id.min_weight and order:
            raise UserError(self.env._("Order below minimum weight of carrier"))
        if parcel:
            shipping_methods = [
                {
                    "id": parcel.get("shipment", {}).get("id"),
                    "weight": int(
                        float(parcel.get("weight", 0)) * 1000
                    ),
                }
            ]
        else:
            shipping_methods = self._acquire_shipping_methods(
                carrier,
                from_country,
                to_country,
                total_weight=total_weight,
                from_postal_code=from_postal_code,
                to_postal_code=to_postal_code,
            )

        if not shipping_methods or (
            len(shipping_methods) == 1 and not shipping_methods[0]
        ):
            raise UserError(
                self.env._(
                    "There is no shipping method available for this order with the selected carrier"
                )
            )

        packages_no = 1
        if order:
            default_package = carrier.sendcloud_default_package_type_id
            target_weight = default_package.max_weight if default_package else False
            target_weight = (
                int(carrier.sendcloud_convert_weight(target_weight, grams=True))
                if target_weight
                else False
            )
            packages_no, total_weight = self._split_shipping(
                carrier.sendcloud_shipping_id, total_weight, target_weight
            )
        if packages_no > 1:
            shipping_methods = [
                m
                for m in shipping_methods
                if m["properties"]["max_weight"]
                == carrier.sendcloud_shipping_id.max_weight
            ]
        shipping_prices = self._get_shipping_prices(
            shipping_methods,
            to_country,
            from_country,
            total_weight,
            from_postal_code,
            to_postal_code,
        )

        if not shipping_prices:
            return None
        shipping_price = min(
            shipping_prices.items(), key=lambda p: float(p[1]["price"])
        )
        price = float(shipping_price[1].get("price")) * packages_no
        currency = shipping_price[1].get("currency")
        currency_id = (
            carrier.env["res.currency"]
            .with_context(active_test=False)
            .search([("name", "=", currency)])
        )
        if not currency_id:
            raise UserError(self.env._("Could not find currency %s", currency))

        to_currency_id = order.currency_id if order else picking.sale_id.currency_id
        converted_price = currency_id._convert(
            price,
            to_currency_id,
            carrier.env.company,
            fields.Date.context_today(carrier),
        )
        return converted_price, packages_no

    def _send_shipment(self, picking, is_return=False):
        sender_id = None
        if not is_return:
            sender_id = self._get_pick_sender_address(picking)
        parcels = self._prepare_parcel(picking, sender_id, is_return)

        if picking.sale_id.pickup_location_data and not is_return:
            for parcel in parcels:
                parcel["to_service_point"] = picking.sale_id.pickup_location_data["id"]

        data = {"parcels": parcels}
        parameters = {
            "errors": "verbose-carrier",
        }
        res = self._send_request("parcels", "post", data, params=parameters)
        res_parcels = res.get("parcels")
        if not res_parcels:
            error_message = res["failed_parcels"][0].get("errors", False)
            raise UserError(
                self.env._(
                    "Something went wrong, parcel not returned from Sendcloud:\n %s'.",
                    error_message,
                )
            )
        return res_parcels

    def _track_shipment(self, parcel_id):
        parcel = self._send_request(f"parcels/{parcel_id}")
        return parcel["parcel"]

    def _cancel_shipment(self, parcel_id):
        return self._send_request(f"parcels/{parcel_id}/cancel", method="post")

    def _get_document(self, url):
        self.logger(f"get {url}", "sendcloud get document")
        try:
            res = self.session.request(method="get", url=url, timeout=60)
        except Exception as err:
            self.logger(str(err), f"sendcloud response {url}")
            raise UserError(
                self.env._(
                    "Sendcloud is not responding. Check your credentials and/or retry later."
                )
            ) from err

        self.logger(f"{res.content}", "sendcloud get document response")
        if res.status_code != 200:
            raise UserError(self.env._("Could not get document!"))
        return res.content

    def _get_addresses(self):
        res = self._send_request("user/addresses/sender")
        return res.get("sender_addresses", [])

    def _split_shipping(
        self, shipping_product_id, total_weight, target_weight=False
    ) -> tuple:
        shipping_count = 1
        shipping_weight = total_weight
        max_weight = target_weight or shipping_product_id.max_weight - 1
        if target_weight or total_weight > max_weight:
            shipping_count = math.ceil(total_weight / max_weight)
            shipping_weight = max_weight
        return shipping_count, shipping_weight

    def _get_shipping_prices(
        self,
        shipping_methods,
        to_country,
        from_country,
        weight=None,
        from_postal_code=None,
        to_postal_code=None,
    ):
        shipping_prices = {}
        params = {
            "shipping_method_id": None,
            "to_country": to_country,
            "from_country": from_country,
            "weight": weight,
            "weight_unit": "gram",
            "from_postal_code": from_postal_code,
            "to_postal_code": to_postal_code,
        }

        for shipping_method in shipping_methods:
            shipping_id = params["shipping_method_id"] = shipping_method["id"]
            if not weight:
                params["weight"] = (
                    shipping_method["properties"]["max_weight"] - 1
                )
            res = self._send_request("shipping-price", params=params)[0]
            if res.get("price"):
                shipping_prices[shipping_id] = res
            elif shipping_id == 8:
                shipping_prices = {8: {"price": 0.0, "currency": "EUR"}}
        return shipping_prices

    def _acquire_shipping_methods(
        self,
        carrier_id,
        from_country,
        to_country,
        total_weight=None,
        is_return=False,
        sizes=None,
        from_postal_code=None,
        to_postal_code=None,
    ) -> list[dict[str, Any]] | None:
        sendcloud_product_id = (
            carrier_id.sendcloud_return_id
            if is_return
            else carrier_id.sendcloud_shipping_id
        )
        if not sendcloud_product_id:
            return None
        shipping_code = sendcloud_product_id.sendcloud_code
        shipping_carrier = sendcloud_product_id.carrier
        single_shipping = (
            total_weight and total_weight < sendcloud_product_id.max_weight
        )
        if single_shipping:
            shipping_products = self._get_shipping_products(
                from_country,
                is_return=is_return,
                carrier=shipping_carrier,
                to_country=to_country,
                weight=total_weight,
                sizes=sizes,
                from_postal_code=from_postal_code,
                to_postal_code=to_postal_code,
            )
        else:
            shipping_products = self._get_shipping_products(
                from_country,
                is_return=is_return,
                carrier=shipping_carrier,
                to_country=to_country,
                sizes=sizes,
                from_postal_code=from_postal_code,
                to_postal_code=to_postal_code,
            )

        shipping_product = next(
            filter(lambda p: p["code"] == shipping_code, shipping_products), None
        )
        if not shipping_product:
            if single_shipping:
                return self._acquire_shipping_methods(
                    carrier_id,
                    from_country,
                    to_country,
                    is_return=is_return,
                    sizes=sizes,
                    from_postal_code=from_postal_code,
                    to_postal_code=to_postal_code,
                )
            else:
                return None

        if not single_shipping:
            max_allowed_weight = shipping_product[
                "weight_range"
            ][
                "max_weight"
            ]
            if sendcloud_product_id.max_weight != max_allowed_weight:
                sendcloud_product_id.max_weight = max_allowed_weight

        user_filters = (
            None if is_return else carrier_id.sendcloud_product_functionalities
        )
        shipping_ids = self._filter_shipping_method_ids(
            shipping_product["methods"], user_filters
        )

        if not shipping_ids:
            raise UserError(
                self.env._(
                    "There's no shipping method matching all your selected filters for this picking/order."
                )
            )

        return list(
            filter(lambda m: m["id"] in shipping_ids, shipping_product["methods"])
        )

    def _filter_shipping_method_ids(
        self,
        shipping_methods: list[dict[str, Any]],
        user_filters: dict[str, list[str | bool]] | None,
    ) -> set[int]:
        default_shipping_functionalities = None
        try:
            default_shipping_functionalities = self._get_shipping_functionalities()
        except Exception as err:
            _logger.warning("_filter_shipping_method_ids failed", exc_info=True)
            self.logger(str(err), "default shipping functionalities for filtering")

        shipping_ids = {m["id"] for m in shipping_methods}
        if not user_filters:
            return shipping_ids

        def pass_filter(shipping_method, func, options):
            return (
                func not in shipping_method["functionalities"]
                and (
                    "None" in options
                    or (
                        default_shipping_functionalities
                        and default_shipping_functionalities[func]["default_value"]
                        in options
                    )
                )
            ) or (
                func in shipping_method["functionalities"]
                and shipping_method["functionalities"][func] in options
            )

        for func, options in user_filters.items():
            filtered_ids = {
                m["id"] for m in shipping_methods if pass_filter(m, func, options)
            }
            shipping_ids &= filtered_ids
            if not shipping_ids:
                return set()
        return shipping_ids

    def _send_request(
        self, endpoint, method="get", data=None, params=None, route=BASE_URL
    ):

        url = url_join(route, endpoint)
        self.logger(
            f"{url}\n{method}\n{data}\n{params}", f"sendcloud request {endpoint}"
        )
        if method not in ["get", "post"]:
            raise ValueError(f"Unhandled request method {method}")
        try:
            res = self.session.request(
                method=method, url=url, json=data, params=params, timeout=60
            )
            self.logger(
                f"{res.status_code} {res.text}", f"sendcloud response {endpoint}"
            )
            res = res.json()
        except Exception as err:
            self.logger(str(err), f"sendcloud response {endpoint}")
            raise UserError(
                self.env._(
                    "Sendcloud is not responding. Check your credentials and/or retry later."
                )
            ) from err

        if "error" in res:
            raise UserError(res["error"]["message"])
        return res

    def _prepare_parcel_items(self, packages, carrier, products_values=None):
        if not isinstance(packages, list):
            packages = [packages]
        if not products_values:
            products_values = {}
        parcel_items = {}
        for pkg in packages:
            for commodity in pkg.commodities:
                key = commodity.product_id.id
                if key in parcel_items:
                    parcel_items[key]["quantity"] += commodity.qty
                    continue

                if commodity.product_id.id in products_values:
                    value = products_values[commodity.product_id.id]["avg_value"]
                else:
                    value = commodity.monetary_value

                hs_code = commodity.product_id.hs_code or ""
                for ch in [" ", "."]:
                    hs_code = hs_code.replace(ch, "")
                parcel_items[key] = {
                    "description": commodity.product_id.name,
                    "quantity": commodity.qty,
                    "weight": float_repr(
                        carrier.sendcloud_convert_weight(commodity.product_id.weight), 3
                    ),
                    "value": round(value, 2),
                    "hs_code": hs_code[:12],
                    "origin_country": commodity.country_of_origin or "",
                    "sku": commodity.product_id.barcode or "",
                }
        return list(parcel_items.values())

    def _get_house_number(self, address):
        house_number = re.search(
            r"(\d+(?:[-\/]?\d+)* ?[a-zA-Z]?\d*)(?![a-zA-Z])", address
        )
        if house_number:
            return house_number.group()
        return " "

    def _check_partner_details(self, partner) -> None:
        if not partner.phone_ids._primary().number:
            raise UserError(
                self.env._("%(partner_name)s phone required", partner_name=partner.name)
            )
        if not partner.email:
            raise UserError(
                self.env._("%(partner_name)s email required", partner_name=partner.name)
            )
        if not all([partner.street, partner.city, partner.zip, partner.country_id]):
            raise UserError(
                self.env._(
                    "The %s address needs to have the street, city, zip, and country",
                    partner.name,
                )
            )
        if (partner.street and len(partner.street) > 75) or (
            partner.street2 and len(partner.street2) > 75
        ):
            raise UserError(
                self.env._(
                    "Each address line can only contain a maximum of 75 characters. You can split the address into multiple lines to try to avoid this limitation."
                )
            )

    def _get_max_package_sizes(self, package_ids):
        sizes = {
            "length": 0,
            "height": 0,
            "width": 0,
        }
        for pkg in package_ids:
            for axis in ("length", "height", "width"):
                sizes[axis] = max(sizes[axis], pkg.dimension.get(axis))
        return sizes

    def _prepare_parcel(self, picking, sender_id, is_return):
        carrier_id = picking.carrier_id
        delivery_packages = carrier_id._get_packages_from_picking(
            picking, carrier_id.sendcloud_default_package_type_id
        )
        if any(not pkg.weight for pkg in delivery_packages):
            raise UserError(
                self.env._(
                    "Ensure picking has shipping weight, if using packages, each package should have a shipping weight"
                )
            )
        to_partner_id = picking.partner_id
        from_partner_id = picking.picking_type_id.warehouse_id.partner_id
        if is_return:
            to_partner_id, from_partner_id = from_partner_id, to_partner_id
        from_country, to_country = (
            from_partner_id.country_id.code,
            to_partner_id.country_id.code,
        )
        from_postal_code, to_postal_code = from_partner_id.zip, to_partner_id.zip
        self._check_partner_details(to_partner_id)
        shipping_weight = int(
            carrier_id.sendcloud_convert_weight(picking.shipping_weight, grams=True)
        )
        to_europe = (
            to_partner_id.country_id
            and "EU" in to_partner_id.country_id.country_group_codes
        )
        use_multicollo = carrier_id.sendcloud_use_batch_shipping and to_europe
        single_shipping = len(delivery_packages) == 1 or (
            use_multicollo and len(delivery_packages) <= 20
        )
        api_weight = (
            int(shipping_weight / len(delivery_packages)) if single_shipping else None
        )

        shipping_methods = self._acquire_shipping_methods(
            picking.carrier_id,
            from_country,
            to_country,
            api_weight,
            is_return,
            from_postal_code=from_postal_code,
            to_postal_code=to_postal_code,
        )
        sendcloud_product_id = (
            carrier_id.sendcloud_return_id
            if is_return
            else carrier_id.sendcloud_shipping_id
        )
        user_uom_max_weight = carrier_id.sendcloud_convert_weight(
            sendcloud_product_id.max_weight - 1, grams=True, reverse=True
        )
        user_weight_uom = (
            carrier_id.env["product.template"].sudo()._get_uom_from_setting("weight")
        )
        if not shipping_methods:
            raise UserError(
                self.env._(
                    "There is no shipping method available for this picking with the selected carrier"
                )
            )
        if any(
            float_compare(
                pkg.weight,
                user_uom_max_weight,
                precision_rounding=user_weight_uom.rounding,
            )
            > 0
            for pkg in delivery_packages
        ):
            overweight_products = picking.move_ids.filtered(
                lambda m: (
                    float_compare(
                        m.product_id.weight,
                        user_uom_max_weight,
                        precision_rounding=m.product_uom_id.rounding,
                    )
                    > 0
                )
            ).product_id
            not_packed = bool(
                not picking.move_line_ids.result_package_id and picking.weight_bulk
            )
            if not_packed:
                message = self.env._(
                    "The total weight of your transfer is too heavy for the heaviest available shipping method."
                )
            else:
                message = self.env._(
                    "Some packages in your transfer are too heavy for the heaviest available shipping method."
                )
            message += self.env._(
                "\nTry to distribute your products across your packages so that they weigh less than %(max_weight)s %(unit)s or choose another carrier.",
                max_weight=user_uom_max_weight,
                unit=user_weight_uom.name,
            )
            if overweight_products:
                product_moves = format_list(
                    picking.env, overweight_products.mapped("name")
                )
                message += self.env._(
                    """\nAdditionally, some individual product(s) are too heavy for the heaviest available shipping method.
                             \nDivide the quantity of the following product(s) across your packages if possible or choose another carrier:\n\t%s""",
                    product_moves,
                )
            raise UserError(message)

        shipping_prices = self._get_shipping_prices(
            shipping_methods,
            to_country,
            from_country,
            from_postal_code=from_postal_code,
            to_postal_code=to_postal_code,
        )
        for shipping_method in reversed(shipping_methods):
            price = shipping_prices.get(shipping_method["id"], {}).get("price")
            shipping_method["price"] = float(price) if price else 0.0

        method_shipments = self._get_method_by_package(
            carrier_id, delivery_packages, shipping_methods, use_multicollo
        )
        parcel_common = self._prepare_parcel_common_data(picking, is_return, sender_id)
        products_values = self._get_sale_totals_by_product(picking.sale_id)

        total_value = 0.0
        if picking.sale_id:
            total_value = sum(
                line.price_total
                for line in picking.sale_id.line_ids.filtered(
                    lambda l: l.product_id.type == "consu" and not l.display_type
                )
            )
        else:
            total_value = sum(
                line.product_id.lst_price * line.product_qty
                for line in picking.move_ids
            )
        total_value = float_repr(total_value, 2)

        parcels = []
        for shipping in method_shipments:
            parcel_common["shipment"] = {
                "id": shipping["id"],
            }
            for pkg in shipping[
                "packages"
            ]:
                parcel = dict(parcel_common)
                if isinstance(pkg, list):
                    max_sizes = self._get_max_package_sizes(pkg)
                    parcel.update(
                        {
                            "weight": float_repr(
                                (sum(p.weight for p in pkg) / len(pkg)), 3
                            ),
                            "length": max_sizes["length"],
                            "width": max_sizes["width"],
                            "height": max_sizes["height"],
                            "quantity": len(pkg),
                        }
                    )
                else:
                    parcel.update(
                        {
                            "weight": float_repr(pkg.weight, 3),
                            "length": pkg.dimension["length"],
                            "width": pkg.dimension["width"],
                            "height": pkg.dimension["height"],
                        }
                    )

                parcel["parcel_items"] = self._prepare_parcel_items(
                    pkg, carrier_id, products_values
                )
                parcel["total_order_value"] = total_value
                parcels.append(parcel)

        return parcels

    def _get_method_by_package(
        self, carrier_id, delivery_packages, shipping_methods, use_multicollo=False
    ):
        sorted_methods = self._get_cheapest_method_by_weight_ranges(shipping_methods)
        failed_assignation = []
        for package in delivery_packages:
            sendcloud_uom_package_weight = int(
                carrier_id.sendcloud_convert_weight(package.weight, grams=True)
            )
            cheapest_method = next(
                (
                    m
                    for m in sorted_methods
                    if m["weight"]["min"]
                    <= sendcloud_uom_package_weight
                    <= m["weight"]["max"]
                ),
                None,
            )
            if cheapest_method:
                cheapest_method["packages"].append(package)
            else:
                failed_assignation.append(package)

        if failed_assignation:
            details = "\n\t- ".join(
                f"{pkg.name}: {pkg.weight}" for pkg in failed_assignation
            )
            raise UserError(
                self.env._(
                    "There's no method with matching weight range for packages :\n%s\nYou can either choose another carrier, change your filters or redefine the content of your package(s)."
                )
                % details
            )

        sorted_methods = [
            m for m in sorted_methods if m["packages"]
        ]
        if not use_multicollo:
            return sorted_methods

        multicollo_batch = [
            {
                "id": False,
                "packages": [[]],
            }
        ]
        pkg_number = math.ceil(len(delivery_packages) / MULTICOLLO_MAX_PACKAGE)
        min_batch_size = len(delivery_packages) % MULTICOLLO_MAX_PACKAGE
        max_batch_size = MULTICOLLO_MAX_PACKAGE
        for method in reversed(sorted_methods):
            while True:
                batch_size = len(multicollo_batch[-1]["packages"][-1])
                method_pkg_size = len(method["packages"])
                if not multicollo_batch[-1]["id"]:
                    multicollo_batch[-1]["id"] = method["id"]

                if (batch_size + method_pkg_size) <= max_batch_size:
                    multicollo_batch[-1]["packages"][-1].extend(method["packages"])
                    break
                to_fulfill = max_batch_size - batch_size
                multicollo_batch[-1]["packages"][-1].extend(
                    method["packages"][: to_fulfill - 1]
                )
                method["packages"] = method["packages"][to_fulfill:]
                pkg_number -= 1
                max_batch_size = MULTICOLLO_MAX_PACKAGE
                multicollo_batch[-1]["packages"].append([])

            if (
                min_batch_size <= len(multicollo_batch[-1]["packages"][-1])
            ):
                pkg_number -= 1
                if pkg_number == 0:
                    break
                min_batch_size = (
                    min_batch_size - len(multicollo_batch[-1]["packages"][-1])
                ) % 20
                max_batch_size = MULTICOLLO_MAX_PACKAGE
                multicollo_batch.append(
                    {
                        "id": False,
                        "packages": [[]],
                    }
                )
            else:
                max_batch_size = (
                    min_batch_size
                )
        return multicollo_batch

    def _get_sale_totals_by_product(
        self, sale_order=None
    ) -> dict[int, dict[str, float]]:
        products_values = {}
        if not sale_order:
            return products_values

        for line in sale_order.line_ids:
            if (
                not line.product_id
                or line.product_id.type == "consu"
                or line.display_type
                or float_is_zero(
                    line.product_uom_qty,
                    precision_rounding=line.product_uom_id.rounding,
                )
                or line.product_uom_qty < 0
            ):
                continue
            if line.product_id.id in products_values:
                products_values[line.product_id.id]["tot_qty"] += line.product_uom_qty
                products_values[line.product_id.id]["tot_value"] += line.price_total
            else:
                products_values[line.product_id.id] = {
                    "tot_qty": line.product_uom_qty,
                    "tot_value": line.price_total,
                }
        for val in products_values.values():
            val.update({"avg_value": float(val["tot_value"]) / float(val["tot_qty"])})
        return products_values

    def _get_cheapest_method_by_weight_ranges(self, shipping_methods):
        shipping_methods = sorted(
            shipping_methods,
            key=lambda m: (
                m["properties"]["min_weight"],
                m["properties"]["max_weight"],
                m["price"],
            ),
        )
        sorted_methods = []
        for method in shipping_methods:
            if (
                sorted_methods
                and method["properties"]["min_weight"]
                == sorted_methods[-1]["weight"]["min"]
                and method["properties"]["max_weight"]
                == sorted_methods[-1]["weight"]["max"]
            ):
                continue
            sorted_methods.append(
                {
                    "id": method["id"],
                    "price": method["price"],
                    "weight": {
                        "min": method["properties"]["min_weight"],
                        "max": method["properties"]["max_weight"],
                    },
                    "packages": [],
                }
            )

        return sorted(sorted_methods, key=lambda m: m["price"])

    def _prepare_parcel_common_data(self, picking, is_return, sender_id=False):
        if picking.sale_id.pickup_location_data:
            if not picking.partner_id.parent_id:
                raise UserError(
                    self.env._(
                        "The delivery address of the customer has been removed from the pickup location. This information is required by Sendcloud. Please go to the delivery partner via the delivery order and make sure the parent of the delivery partner is the partner you want to ship to."
                    )
                )
            to_partner_id = picking.partner_id.parent_id
        else:
            to_partner_id = picking.partner_id
        from_partner_id = picking.picking_type_id.warehouse_id.partner_id
        if is_return:
            to_partner_id, from_partner_id = from_partner_id, to_partner_id
        carrier_id = picking.carrier_id
        apply_rules = carrier_id.sendcloud_shipping_rules
        sendcloud_product_id = (
            carrier_id.sendcloud_return_id
            if is_return
            else carrier_id.sendcloud_shipping_id
        )

        if picking.sale_id:
            currency_name = picking.sale_id.currency_id.name
            shipping_cost = sum(
                sol.price_total for sol in picking.sale_id.line_ids if sol.is_delivery
            )
        else:
            currency_name = picking.company_id.currency_id.name
            shipping_cost = sum(ml.sale_price for ml in picking.move_line_ids)

        parcel_common = {
            "name": (to_partner_id.name or to_partner_id.parent_id.name or "")[:75],
            "company_name": to_partner_id.commercial_company_name[:50]
            if to_partner_id.commercial_company_name
            else "",
            "address": to_partner_id.street,
            "address_2": to_partner_id.street2 or "",
            "house_number": self._get_house_number(to_partner_id.street),
            "city": to_partner_id.city or "",
            "country_state": to_partner_id.state_id.code or "",
            "postal_code": to_partner_id.zip,
            "country": to_partner_id.country_id.code,
            "telephone": to_partner_id.phone_ids._primary().number or "",
            "email": to_partner_id.email or "",
            "request_label": True,
            "apply_shipping_rules": apply_rules,
            "is_return": is_return,
            "shipping_method_checkout_name": sendcloud_product_id.name,
            "order_number": picking.sale_id.name or picking.name,
            "total_order_value_currency": currency_name,
            "customs_information": {
                "customs_shipment_type": 4 if is_return else 2,
                "customs_invoice_nr": picking.sale_id.invoice_ids[:1].name
                or picking.origin
                or "",
                "freight_costs": float_repr(shipping_cost, 2),
            },
        }
        if sender_id:
            parcel_common.update({"sender_address": sender_id})
        elif from_partner_id:
            self._check_partner_details(from_partner_id)
            parcel_common.update(
                {
                    "from_name": (
                        from_partner_id.name or from_partner_id.parent_id.name or ""
                    )[:75],
                    "from_company_name": from_partner_id.commercial_company_name[:50]
                    if from_partner_id.commercial_company_name
                    else "",
                    "from_house_number": self._get_house_number(from_partner_id.street),
                    "from_address_1": from_partner_id.street or "",
                    "from_address_2": from_partner_id.street2 or "",
                    "from_city": from_partner_id.city or "",
                    "from_state": from_partner_id.state_id.code or "",
                    "from_postal_code": from_partner_id.zip or "",
                    "from_country": from_partner_id.country_id.code,
                    "from_telephone": from_partner_id.phone_ids._primary().number or "",
                    "from_email": from_partner_id.email or "",
                }
            )
        return parcel_common

    def _get_pick_sender_address(self, picking):
        warehouse_name = picking._get_warehouse_name().lower().replace(" ", "")
        addresses = self._get_addresses()
        res_id = None
        for addr in addresses:
            label = addr.get("label", "").lower().replace(" ", "")
            contact_name = addr.get("contact_name", "").lower().replace(" ", "")
            if warehouse_name in (label, contact_name):
                res_id = addr["id"]
                break
        if not res_id:
            raise UserError(
                self.env._(
                    "No address found with contact name %s on your sendcloud account.",
                    picking.location_id.warehouse_id.name,
                )
            )
        return res_id
