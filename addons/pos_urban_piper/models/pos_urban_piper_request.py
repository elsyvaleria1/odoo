import json
import logging
from datetime import datetime
from urllib.parse import quote

import requests

from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.tools import format_duration, html2plaintext
from odoo.tools.urls import urljoin as url_join

_logger = logging.getLogger(__name__)

EVENT_TYPES = [
    "store_creation",
    "store_action",
    "inventory_update",
    "item_state_toggle",
    "order_placed",
    "order_status_update",
    "rider_status_update",
]
UP_LANGUAGES = ["hi", "ar", "ja", "pt", "fr", "es"]


class UrbanPiperClient:
    def __init__(self, config) -> None:
        self.config = config
        self.db_uuid = self.config.env.registry.settings.get(
            self.config.env, "database.uuid", False
        )

    def _api_key(self):
        return self.config.env.company.with_privilege(
            "point_of_sale.privilege_spend_terminal_credentials",
            reason="a request of the point of sale to UrbanPiper",
        ).pos_urbanpiper_apikey

    def _send_api_request(self, endpoint, method="POST", data=None, timeout=10):
        headers = {
            "Authorization": f"apikey {self.config.env.company.pos_urbanpiper_username}:"
            f"{self._api_key()}",
            "Content-Type": "application/json",
        }
        urbanpiper_url = (
            "https://pos-int.urbanpiper.com/"
            if self.config.env.registry.settings.get(
                self.config.env, "pos_urban_piper.is_production_mode", False
            )
            == "False"
            else "https://api.urbanpiper.com/"
        )
        access_url = urbanpiper_url + endpoint
        pos_config = self.config
        try:
            response = pos_config._get_integration_connection()._egress_request(
                method,
                access_url,
                purpose="urban_piper",
                json=data,
                headers=headers,
                timeout=timeout,
            )
            response_json = response.json()
            pos_config.log_xml(
                "API Request Successful:\nURL: %s \nMethod: %s \nPayload: %s \nResponse: %s"
                % (access_url, method, json_dumps(data), json_dumps(response_json)),
                "_send_api_request",
                "Urbanpiper API Success",
            )
            response.raise_for_status()
            return response_json
        except requests.exceptions.ConnectionError as error:
            _logger.warning(
                "Connection Error: %r with the given URL %r", error, access_url
            )
            pos_config.log_xml(
                "Connection Error: %s \nURL: %s \nMethod: %s \nPayload: %s"
                % (error, access_url, method, json_dumps(data)),
                "_send_api_request",
                "Urbanpiper API Connection Error",
            )
            return {
                "errors": {
                    "timeout": "Cannot reach the server. Please try again later."
                }
            }
        except requests.exceptions.HTTPError as error:
            message = response_json.get("message")
            pos_config.log_xml(
                "HttpError: %s \nURL: %s \nMethod: %s \nPayload: %s"
                % (message or error, access_url, method, json_dumps(data)),
                "_send_api_request",
                "Urbanpiper API HTTP Error",
            )
            _logger.warning("HTTPError: %r", message or error)
            return {"errors": {"HTTPError": message or str(error)}}
        except requests.exceptions.JSONDecodeError as error:
            _logger.warning("JSONDecodeError: %r", error)
            return {"errors": {"JSONDecodeError": "Failed to parse server response."}}
        except json.decoder.JSONDecodeError as error:
            _logger.warning("JSONDecodeError: %r", error)
            pos_config.log_xml(
                "JSONDecodeError: %s \nURL: %s \nMethod: %s \nPayload: %s"
                % (error, access_url, method, json_dumps(data)),
                "_send_api_request",
                "Urbanpiper API JSON Decode Error",
            )
            return {"errors": {"JSONDecodeError": "Failed to parse server response."}}

    def configure_webhook(self) -> None:
        base_url = self.config.get_base_url()
        if base_url != self.config.urbanpiper_webhook_url:
            self.config.urbanpiper_webhook_url = base_url
            self._register_webhook()

    def _register_webhook(self) -> None:
        endpoint = "external/api/v1/webhooks/"
        base_url = self.config.urbanpiper_webhook_url
        webhook_url = url_join(base_url, "/urbanpiper/webhook/")
        for event_type in EVENT_TYPES:
            controller_url = url_join(webhook_url, event_type)
            payload = {
                "active": True,
                "event_type": event_type,
                "retrial_interval_units": "seconds",
                "url": controller_url,
                "headers": {
                    "X-Urbanpiper-Uuid": self.config.env.registry.settings.get(
                        self.config.env, "pos_urban_piper.uuid", False
                    )
                },
            }
            self._send_api_request(endpoint, data=payload)

    def request_store_create(self):
        endpoint = "external/api/v1/stores/"
        data = {
            "stores": [
                {
                    "name": self.config.with_context(lang="en_US").name,
                    "city": self.config.company_id.city,
                    "ref_id": self.config.urbanpiper_store_identifier,
                }
            ]
        }
        name_translations = self.config.get_field_translations("name")
        data["stores"][0]["translations"] = self._get_translations(
            name_translations, "name"
        )
        data = self.config.prepare_store_data(data)
        return self._send_api_request(endpoint, data=data)

    def request_sync_menu(self):
        store_identifier = quote(self.config.urbanpiper_store_identifier, safe="")
        endpoint = f"external/api/v1/inventory/locations/{store_identifier}/"
        product_domain = [
            ("urbanpiper_pos_config_ids", "in", self.config.ids),
            ("type", "!=", "combo"),
        ]
        full_sync_required_providers = ["justeat", "grubhub", "doordash", "ubereats"]
        products = self.config.env["product.template"].search(product_domain)
        pos_products = products
        flush = self.config.env.context.get("flush")
        if not flush and not any(
            provider.technical_name in full_sync_required_providers
            for provider in self.config.urbanpiper_delivery_provider_ids
        ):
            pos_products = products.filtered(
                lambda product: (
                    not product.urban_piper_status_ids
                    or self.config.id
                    not in product.urban_piper_status_ids.config_id.ids
                    or any(
                        ups.config_id.id in self.config.ids
                        and not ups.is_product_linked
                        for ups in product.urban_piper_status_ids
                    )
                )
            )
        pos_products_without_pos_categ_ids = pos_products.filtered(
            lambda p: not p.pos_categ_ids
        )
        pos_other_categ_id = self.config.env["pos.category"].search(
            [("name", "ilike", "other")], limit=1
        )
        if not pos_other_categ_id:
            pos_other_categ_id = self.config.env["pos.category"].create(
                {
                    "name": "Other",
                }
            )
        pos_products_without_pos_categ_ids.pos_categ_ids = pos_other_categ_id
        pos_categories = pos_products.pos_categ_ids
        pos_categories |= pos_categories.parent_id
        pos_attribute_products = pos_products.filtered(lambda p: p.attribute_line_ids)
        payload = {
            "flush_categories": flush,
            "categories": self._prepare_categories_data(pos_categories),
            "flush_items": flush,
            "items": self._prepare_items_data(pos_products),
            "flush_option_groups": flush,
            "option_groups": self._prepare_option_groups_data(pos_attribute_products),
            "flush_options": flush,
            "options": self._prepare_option_data(pos_attribute_products),
            "flush_taxes": flush,
            "taxes": self.config.prepare_taxes_data(pos_products),
            "flush_charges": flush,
            "charges": self._prepare_charges_data(),
        }
        response_json = self._send_api_request(
            endpoint, method="POST", data=payload, timeout=90
        )
        if response_json.get("status") == "success":
            for product in pos_products:
                if not product.urban_piper_status_ids or (
                    product.urban_piper_status_ids
                    and self.config.id
                    not in product.urban_piper_status_ids.config_id.ids
                ):
                    product.write(
                        {
                            "urban_piper_status_ids": [
                                Command.create(
                                    {
                                        "product_tmpl_id": product.id,
                                        "is_product_linked": True,
                                        "config_id": self.config.id,
                                    }
                                )
                            ]
                        }
                    )
                elif (
                    product.urban_piper_status_ids
                    and self.config.id in product.urban_piper_status_ids.config_id.ids
                ):
                    product.urban_piper_status_ids.filtered(
                        lambda p: p.config_id == self.config
                    ).write({"is_product_linked": True})
        if response_json.get("status") == "success":
            self.config.urbanpiper_last_sync_date = datetime.now()
        return response_json

    def _get_translations(self, field_translations, field):
        translations = []
        for translation in field_translations[0]:
            lang = translation["lang"].split("_")[0]
            translations.append(
                {"language": lang, field: translation["value"]}
            ) if lang in UP_LANGUAGES else None
        return translations

    def get_item_ref_id(self, product) -> str:
        return f"{product.id}-{self.db_uuid[0:5]}"

    def _prepare_categories_data(self, pos_categories):
        category_lst = []
        for category in pos_categories:
            categ_dict = {
                "ref_id": str(category.id),
                "name": category.with_context(lang="en_US").name,
                "sort_order": category.sequence,
                "active": True,
                "img_url": self._get_or_create_public_image_url(category),
            }
            if category.parent_id:
                categ_dict["parent_ref_id"] = str(category.parent_id.id)
            name_translations = category.get_field_translations("name")
            categ_dict["translations"] = self._get_translations(
                name_translations, "name"
            )
            category_lst.append(categ_dict)
        return category_lst

    def _prepare_items_data(self, pos_products):
        item_lst = []
        for product in pos_products:
            product_price = (
                product.list_price
                if not self.config.urbanpiper_pricelist_id
                else self.config.urbanpiper_pricelist_id.sudo()._get_product_price(
                    product, 1.0, uom=product.uom_id
                )
            )
            item = {
                "ref_id": self.get_item_ref_id(product),
                "title": product.with_context(lang="en_US").name,
                "description": html2plaintext(
                    product.with_context(lang="en_US").public_description
                )
                if product.public_description
                else "",
                "price": product.taxes_id._filter_taxes_by_company(
                    self.config.company_id
                ).compute_all(product_price, product.currency_id, 1)[
                    self.config._get_total_tax_tag()
                ],
                "weight": product.weight,
                "food_type": product.urbanpiper_meal_type,
                "category_ref_ids": [str(i) for i in product.pos_categ_ids.ids],
                "recommended": product.is_recommended_on_urbanpiper,
                "img_url": self._get_or_create_public_image_url(product),
                "available": True,
                "included_platforms": (
                    [
                        provider.technical_name
                        for provider in (
                            product.urbanpiper_pos_platform_ids
                            & self.config.urbanpiper_delivery_provider_ids
                        )
                    ]
                ),
            }
            name_translations = product.get_field_translations("name")
            description_translations = product.get_field_translations(
                "public_description"
            )
            name_dict = {
                t["lang"].split("_")[0]: t["value"]
                for t in name_translations[0]
                if t["lang"].split("_")[0] in UP_LANGUAGES
            }
            desc_dict = {
                t["lang"].split("_")[0]: t["value"]
                for t in description_translations[0]
                if t["lang"].split("_")[0] in UP_LANGUAGES
            }
            translations = [
                {
                    "language": lang,
                    "title": name_dict.get(lang, ""),
                    "description": desc_dict.get(lang, ""),
                }
                for lang in UP_LANGUAGES
                if lang in name_dict or lang in desc_dict
            ]
            item["translations"] = translations
            for provider in (
                product.urbanpiper_pos_platform_ids
                & self.config.urbanpiper_delivery_provider_ids
            ):
                tags = item.setdefault("tags", {})
                alcohol_tags = tags.setdefault(provider.technical_name, [])
                alcohol_tag = (
                    "alcohol-present"
                    if product.is_alcoholic_on_urbanpiper
                    else "alcohol-absent"
                )
                alcohol_tags.append(alcohol_tag)
            updated_item = self.config.update_urbanpiper_item_data(item, product)
            item_lst.append(updated_item)
        return item_lst

    def _prepare_option_groups_data(self, pos_products):
        attribute_lst = []
        for product in pos_products:
            for attr_line in product.attribute_line_ids:
                group = {
                    "ref_id": f"{product.id}-{attr_line.attribute_id.id}",
                    "title": attr_line.attribute_id.with_context(lang="en_US").name,
                    "active": True,
                    "multi_options_enabled": bool(
                        attr_line.attribute_id.display_type == "multi"
                    ),
                    "item_ref_ids": [self.get_item_ref_id(product)],
                    "min_selectable": 0,
                    "max_selectable": 30
                    if any(
                        provider.technical_name == "doordash"
                        for provider in self.config.urbanpiper_delivery_provider_ids
                    )
                    else -1,
                }
                if attr_line.attribute_id.display_type != "multi":
                    group["min_selectable"] = 1
                    group["max_selectable"] = 1
                name_translations = attr_line.attribute_id.get_field_translations(
                    "name"
                )
                group["translations"] = self._get_translations(
                    name_translations, "title"
                )
                attribute_lst.append(group)
        return attribute_lst

    def _prepare_option_data(self, pos_products):
        value_lst = []
        active_ptav = (
            pos_products.attribute_line_ids.product_template_value_ids.filtered(
                lambda ptav: ptav.ptav_active
            )
        )
        for option in active_ptav:
            value_dict = {
                "ref_id": f"{option.product_tmpl_id.id}-{option.product_attribute_value_id.id}",
                "title": option.product_attribute_value_id.with_context(
                    lang="en_US"
                ).name,
                "available": True,
                "opt_grp_ref_ids": [
                    f"{option.product_tmpl_id.id}-{i}" for i in option.attribute_id.ids
                ],
                "price": option.price_extra
                or option.product_attribute_value_id.default_extra_price,
                "food_type": option.product_tmpl_id.urbanpiper_meal_type,
            }
            name_translations = (
                option.product_attribute_value_id.get_field_translations("name")
            )
            value_dict["translations"] = self._get_translations(
                name_translations, "title"
            )
            value_lst.append(value_dict)
        return value_lst

    def _prepare_charges_data(self) -> list:
        product_packaging = self.config.env.ref(
            "pos_urban_piper.product_packaging_charges", False
        )
        product_delivery = self.config.env.ref(
            "pos_urban_piper.product_delivery_charges", False
        )

        def get_charge_data(product):
            return {
                "code": "PC_F" if product == product_packaging else "DC_F",
                "title": product.with_context(lang="en_US").name,
                "active": True,
                "structure": {
                    "applicable_on": "order.order_subtotal",
                    "value": product.list_price,
                },
                "item_ref_ids": ["all"],
            }

        return [
            get_charge_data(product)
            for product in [product_packaging, product_delivery]
            if product and product.list_price > 0
        ]

    def request_category_timing(self):
        endpoint = "external/api/v1/inventory/categories/timing-groups/"
        pos_categories = (
            self.config.env["pos.category"]
            .search([])
            .filtered(lambda categ: (categ.hour_until - categ.hour_after) != 0)
        )
        timing_groups = []
        week_days = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        for category in pos_categories:
            day_slots = [
                {
                    "day": day,
                    "slots": [
                        {
                            "start_time": "23:59"
                            if category.hour_after >= 24.0
                            else format_duration(category.hour_after),
                            "end_time": "23:59"
                            if category.hour_until >= 24.0
                            else format_duration(category.hour_until),
                        }
                    ],
                }
                for day in week_days
            ]
            timing_groups.append(
                {
                    "title": f"{category.name} timings",
                    "category_ref_ids": [str(category.id)],
                    "day_slots": day_slots,
                }
            )
        payload = {"timing_groups": timing_groups}
        return self._send_api_request(endpoint, method="POST", data=payload)

    def register_item_toggle(self, products, status):
        product_lst_str = [self.get_item_ref_id(product) for product in products]
        endpoint = "hub/api/v1/items/"
        payload = {
            "location_ref_id": self.config.urbanpiper_store_identifier,
            "item_ref_ids": product_lst_str,
            "option_ref_ids": [],
            "action": "enable" if status else "disable",
        }
        response_json = self._send_api_request(endpoint, method="POST", data=payload)
        if response_json.get("status") == "success":
            self.config._notify(
                "PRODUCT_UP_STATUS_CHANGED",
                {
                    "product_ids": [p.id for p in products],
                    "status": status,
                },
            )
        return response_json

    def urbanpiper_attribute_value_toggle(self, values, status):
        value_lst_str = [
            f"{value.product_tmpl_id.id}-{value.product_attribute_value_id.id}"
            for value in values
        ]
        endpoint = "hub/api/v1/items/"
        payload = {
            "location_ref_id": self.config.urbanpiper_store_identifier,
            "item_ref_ids": [],
            "option_ref_ids": value_lst_str,
            "action": "enable" if status else "disable",
        }
        return self._send_api_request(endpoint, method="POST", data=payload)

    def request_status_update(
        self, order_id, new_status, prep_time, code=None
    ) -> tuple:
        endpoint = f"external/api/v1/orders/{order_id}/status/"
        payload = {
            "new_status": new_status,
            "reason_code": code,
        }
        if new_status == "Acknowledged":
            payload["extra"] = {
                "prep_time_mins": prep_time,
            }
        response_json = self._send_api_request(endpoint, method="PUT", data=payload)
        if response_json:
            if response_json.get("status") == "success":
                return True, ""
            else:
                return False, response_json.get("message") or next(
                    iter(response_json.get("errors", {}).values()), ""
                )
        else:
            return False, "Failed to update status in Urban Piper"

    def urbanpiper_order_reference_update(self, order) -> None:
        endpoint = f"external/api/v1/orders/{order.delivery_identifier}/"
        payload = {"reference_id": order.name}
        self._send_api_request(endpoint, method="PUT", data=payload)

    def urbanpiper_store_status_update(self, status) -> None:
        provider_name = self.config.env.context.get("provider_name")
        platforms = (
            [provider_name]
            if provider_name
            else [
                p.technical_name for p in self.config.urbanpiper_delivery_provider_ids
            ]
        )
        if platforms:
            payload = {
                "location_ref_id": self.config.urbanpiper_store_identifier,
                "platforms": platforms,
                "action": "enable" if status else "disable",
            }
            self._send_api_request("hub/api/v1/location/", data=payload)

    def _get_jpeg_datas(self, datas):
        try:
            data_uri = (
                self.config.env["ir.qweb"]
                .with_context(webp_as_jpg=True)
                ._get_converted_image_data_uri(datas)
            )
            _header, base64_data = data_uri.split("base64,", 1)
            return base64_data
        except TypeError:
            return datas

    def _get_or_create_public_image_url(self, record) -> str:
        base_url = self.config.urbanpiper_webhook_url
        image_data = (
            record.image_1920
            if record._name == "product.template"
            else record.image_128
        )
        attachment = record.env["ir.attachment"].search(
            [
                ("res_model", "=", record._name),
                ("res_id", "=", record.id),
                ("type", "=", "binary"),
                ("public", "=", True),
                ("mimetype", "=", "image/jpg"),
            ],
            limit=1,
        )
        datas = self._get_jpeg_datas(image_data)
        if attachment:
            attachment.datas = datas
        else:
            attachment = record.env["ir.attachment"].create(
                {
                    "name": record.name,
                    "type": "binary",
                    "datas": datas,
                    "res_model": record._name,
                    "res_id": record.id,
                    "public": True,
                    "mimetype": "image/jpg",
                }
            )
        local_url = attachment.local_url
        return url_join(base_url, local_url)

    def request_refresh_webhooks(self):
        self.config.urbanpiper_webhook_url = self.config.get_base_url()
        self._register_webhook()
        wehbook_json = self._send_api_request(
            "external/api/v1/webhooks?limit=50", method="GET"
        )
        webhooks = wehbook_json.get("webhooks")
        response_json = {}
        if webhooks:
            for webhook in webhooks:
                if (
                    self.config.urbanpiper_webhook_url
                    and self.config.urbanpiper_webhook_url in webhook.get("url")
                ):
                    payload = {
                        "active": True,
                        "event_type": webhook.get("event_type"),
                        "retrial_interval_units": "seconds",
                        "url": webhook.get("url"),
                        "headers": {
                            "X-Urbanpiper-Uuid": self.config.env.registry.settings.get(
                                self.config.env, "pos_urban_piper.uuid", False
                            )
                        },
                    }
                    wehbook_id = webhook.get("webhook_id")
                    response_json = self._send_api_request(
                        f"external/api/v1/webhooks/{wehbook_id}/",
                        data=payload,
                        method="PUT",
                    )
        return response_json
