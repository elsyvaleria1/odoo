import base64
import logging
from datetime import timedelta

import requests
from requests.exceptions import ConnectionError as RequestConnectionError
from requests.exceptions import Timeout as RequestTimeout

from odoo import api, fields, models
from odoo.exceptions import RedirectWarning, UserError

from odoo.addons.product_barcodelookup.tools import barcode_lookup_service

_logger = logging.getLogger(__name__)


class WizardProductProductUpdateImage(models.TransientModel):
    _name = "wizard.product.product.update.image"
    _description = (
        "Fetch product images from Barcode Lookup based on the product's barcode."
    )

    def _check_cron_status(self) -> bool:
        ir_cron = self.env.ref(
            "product_barcodelookup.ir_cron_fetch_image", raise_if_not_found=False
        )
        if not ir_cron:
            raise UserError(
                self.env._(
                    'The scheduled action "Product Images: Get product images from Barcode Lookup" '
                    "has been deleted. Please contact your administrator to have the action restored "
                    'or to reinstall the module "product_barcodelookup".'
                )
            )
        cron_triggers_count = self.env["ir.cron.trigger"].search_count(
            [("cron_id", "=", ir_cron.id)]
        )
        if cron_triggers_count > 0:
            raise UserError(
                self.env._(
                    "A task to process products in the background is already running. "
                    "Please try again later."
                )
            )
        return True

    def _check_api_key_set(self) -> None:
        if not barcode_lookup_service.get_barcode_lookup_key(self):
            action = self.env.ref("base.res_config_setting_act_window")
            msg = self.env._(
                "The API Key for Barcode Lookup must be set in the General Settings."
            )
            raise RedirectWarning(msg, action.id, self.env._("Go to Settings"))

    @api.model
    def default_get(self, fields):
        self._check_cron_status()
        self._check_api_key_set()

        if self.env.context.get("active_model") == "product.template":
            product_ids = (
                self.env["product.template"]
                .browse(self.env.context.get("active_ids"))
                .product_variant_ids
            )
        else:
            product_ids = self.env["product.product"].browse(
                self.env.context.get("active_ids")
            )
        nb_products_selected = len(product_ids)
        products_to_process = product_ids.filtered(
            lambda p: not p.image_1920 and p.barcode
        )
        nb_products_to_process = len(products_to_process)
        nb_products_unable_to_process = nb_products_selected - nb_products_to_process
        defaults = super().default_get(fields)
        defaults.update(
            products_to_process=products_to_process,
            nb_products_selected=nb_products_selected,
            nb_products_to_process=nb_products_to_process,
            nb_products_unable_to_process=nb_products_unable_to_process,
        )
        return defaults

    nb_products_selected = fields.Integer(
        string="Number of selected products",
        readonly=True,
    )
    products_to_process = fields.Many2many(
        comodel_name="product.product",
        help="The list of selected products that meet the criteria (have a barcode and no image)",
    )
    nb_products_to_process = fields.Integer(
        string="Number of products to process",
        readonly=True,
    )
    nb_products_unable_to_process = fields.Integer(
        string="Number of product unprocessable",
        readonly=True,
    )

    def action_fetch_image(self) -> dict:
        self.products_to_process.is_image_fetch_pending = (
            True
        )

        matching_images_count = self._process_products(
            self._get_products_to_process(10)
        )

        if self._get_products_to_process(1):
            self._check_cron_status()
            self.with_context(
                automatically_triggered=False
            )._trigger_update_images_cron()
            message = self.env._(
                "Products are processed in the background. Images will be updated progressively."
            )
            message_type = "success"
        else:
            message = self.env._(
                "%(matching_images_count)s matching images have been found for %(product_count)s "
                "products.",
                matching_images_count=matching_images_count,
                product_count=len(self.products_to_process),
            )
            message_type = "success" if matching_images_count > 0 else "warning"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Product images"),
                "type": message_type,
                "message": message,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _cron_update_images(self) -> None:
        self._process_products(self._get_products_to_process(100))
        if self._get_products_to_process(1):
            self.with_context(automatically_triggered=True)._trigger_update_images_cron(
                fields.Datetime.now() + timedelta(minutes=1.0)
            )

    def _get_products_to_process(self, limit=100):
        products_to_process = self.products_to_process or self.env[
            "product.product"
        ].search([("is_image_fetch_pending", "=", True)], limit=limit)
        return products_to_process.filtered(
            lambda p: not p.image_1920 and p.barcode and p.is_image_fetch_pending
        )[
            :limit
        ]

    def _process_products(self, products_to_process) -> int:
        if not products_to_process:
            return 0

        nb_timeouts = 0
        batch_size = 10
        for i in range(0, len(products_to_process), batch_size):
            batch_products = products_to_process[i : i + batch_size]
            barcodes = [product.barcode for product in products_to_process]

            try:
                response = self._get_image_urls_from_barcode_lookup(barcodes)
                response_status_code = response.get("status_code")

                if response_status_code:
                    if response_status_code == requests.codes.forbidden:
                        raise UserError(
                            self.env._(
                                "The Barcode Lookup API key is not set properly or it is invalid. "
                                "Check your API key in setting and retry."
                            )
                        )
                    if response_status_code == requests.codes.too_many_requests:
                        self.with_context(
                            automatically_triggered=True
                        )._trigger_update_images_cron(
                            fields.Datetime.now() + timedelta(days=1.0)
                        )
                        _logger.warning(
                            "Exceeded API call limits. "
                            "Delegating remaining images to next cron run."
                        )
                        break
                    if response_status_code == requests.codes.not_found:
                        _logger.warning("No data returned for some barcodes.")
            except RequestConnectionError, RequestTimeout:
                nb_timeouts += 1
                if nb_timeouts <= 3:
                    continue

                self.with_context(
                    automatically_triggered=True
                )._trigger_update_images_cron(
                    fields.Datetime.now() + timedelta(hours=1.0)
                )
                _logger.warning(
                    "Encountered too many timeouts. Delegating remaining images to next cron run."
                )
                break

            product_response = response.get("products", False)
            for product in batch_products:
                if (
                    product_response
                    and product.barcode in product_response
                    and product_response[product.barcode]
                ):
                    for image_link in product_response[product.barcode]:
                        try:
                            image = self._get_image_from_url(image_link)
                            if image:
                                product.image_1920 = image
                            break
                        except (
                            RequestConnectionError,
                            RequestTimeout,
                            UserError,
                        ):
                            pass
                product.is_image_fetch_pending = False
                self.env["ir.cron"]._commit_progress(processed=1)

        return len(products_to_process.filtered("image_1920"))

    def _get_image_urls_from_barcode_lookup(self, barcodes):
        if not barcodes:
            return None
        barcodes = ",".join(barcodes)
        response = (
            self.env["product.template"]
            .with_context(skip_barcode_check=True)
            .barcode_lookup(barcodes)
        )
        product_response = response.get("products", False)
        if product_response:
            products = {}
            for product in product_response:
                if all(key in product for key in ["barcode_number", "images"]):
                    products[product.get("barcode_number")] = product.get("images")
            response.update({"products": products})
        return response

    def _get_image_from_url(self, url):
        image = None
        response = barcode_lookup_service.barcode_lookup_request(url)
        if (
            response.status_code == requests.codes.ok
            and "image/" in response.headers.get("Content-Type", "")
        ):
            image = base64.b64encode(response.content)
        return image

    def _trigger_update_images_cron(self, at=None) -> None:
        cron_fetch_image = self.env.ref("product_barcodelookup.ir_cron_fetch_image")
        if at:
            self.env["ir.cron.trigger"].search(
                [
                    ("call_at", "<", at),
                    ("cron_id", "=", cron_fetch_image.id),
                ]
            ).unlink()
        cron_fetch_image._trigger(at)
