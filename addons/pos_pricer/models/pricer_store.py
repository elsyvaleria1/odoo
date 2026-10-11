import logging
import re

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)
PRICER_REQUESTS_TIMEOUT = 10


def setup_requests_session(
    requests_session, pricer_login, pricer_password, auth_url
) -> None:
    try:
        response = requests_session.get(
            auth_url,
            auth=(pricer_login, pricer_password),
            timeout=PRICER_REQUESTS_TIMEOUT,
        )
        response.raise_for_status()
        jwt_token = response.json().get("token")
        requests_session.headers.update({"Authorization": f"Bearer {jwt_token}"})
    except requests.exceptions.RequestException as e:
        _logger.warning(
            "Failed to update the jwt token through Pricer API URL: %s: %s", auth_url, e
        )


class PricerStore(models.Model):
    _name = "pricer.store"
    _inherit = ["mixin.credential.holder", "mixin.integration.connected"]
    _description = "Pricer Store regrouping pricer tags"
    _credential_holder_field = "store_credential_id"
    _credential_purpose = "pos_pricer:store"
    _CREDENTIAL_FIELDS = {
        "pricer_password": "pricer_password",
    }

    name = fields.Char(
        string="Store Name",
        required=True,
        help="Pricer Store name in Odoo database",
    )

    pricer_store_identifier = fields.Char(
        string="Pricer Store ID",
        required=True,
        help="Identifier of the store in the Pricer system",
    )
    store_credential_id = fields.Many2one(
        comodel_name="credential.credential",
        string="Credential",
        copy=False,
        ondelete="restrict",
        groups="base.group_system",
        help="Holds this store's Pricer password.",
    )
    pricer_tenant_name = fields.Char(
        required=True,
        help="Your company identifier at Pricer",
    )
    pricer_login = fields.Char(
        required=True,
        help="Login of your Pricer account",
    )
    pricer_password = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        copy=True,
        required=True,
        help="Password of your Pricer account",
    )

    product_ids = fields.One2many(
        comodel_name="product.product",
        inverse_name="pricer_store_id",
        string="Products",
    )
    pricer_tag_ids = fields.One2many(
        comodel_name="pricer.tag",
        inverse_name="pricer_store_id",
        string="Pricer Tags",
    )

    last_update_datetime = fields.Datetime(
        string="Last Update",
        readonly=True,
        help="Date and time of the last synchronization with Pricer",
    )
    last_update_status_message = fields.Char(
        string="Last Update Status",
        readonly=True,
        help="Status message of the last synchronization with Pricer",
    )

    dummy_prod_barcode = fields.Char(
        string="Product barcode",
        store=False,
        help="Scan the product barcode here",
    )

    dummy_tag_barcode = fields.Char(
        string="Pricer tag barcode",
        store=False,
        help="Scan the Pricer tag barcode here",
    )

    auth_url = fields.Char(compute="_compute_auth_url")
    create_or_update_products_url = fields.Char(
        compute="_compute_create_or_update_products_url"
    )
    link_tags_url = fields.Char(compute="_compute_link_tags_url")

    @api.depends("pricer_tenant_name")
    def _compute_auth_url(self) -> None:
        for record in self:
            record.auth_url = f"https://central-manager.{record.pricer_tenant_name}.pcm.pricer-plaza.com/api/public/auth/v1/login"

    @api.depends("pricer_store_identifier", "pricer_tenant_name")
    def _compute_create_or_update_products_url(self) -> None:
        for record in self:
            record.create_or_update_products_url = f"https://{record.pricer_store_identifier}.{record.pricer_tenant_name}.pcm.pricer-plaza.com/api/public/core/v1/items"

    @api.depends("pricer_store_identifier", "pricer_tenant_name")
    def _compute_link_tags_url(self) -> None:
        for record in self:
            record.link_tags_url = f"https://{record.pricer_store_identifier}.{record.pricer_tenant_name}.pcm.pricer-plaza.com/api/public/core/v1/labels"

    @api.constrains("pricer_store_identifier")
    def _check_pricer_store_identifier(self) -> None:
        for record in self:
            if not re.fullmatch(
                r"^[a-z0-9][a-z0-9-]*$", record.pricer_store_identifier
            ):
                raise ValidationError(
                    self.env._(
                        "Pricer Store ID must only contain lowercase a-z, 0-9 or '-' and not start with '-'"
                    )
                )

    @api.constrains("pricer_tenant_name")
    def _check_pricer_tenant_name(self) -> None:
        for record in self:
            if not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9-]*", record.pricer_tenant_name or ""
            ):
                raise ValidationError(
                    self.env._(
                        "Pricer Tenant Name must only contain letters, digits or '-' and not start with '-'"
                    )
                )

    def _integration_connection_service(self):
        return "pos_pricer", self.env._("Point of Sale: Pricer"), "other"

    def unlink_label(self, pricer_tag_id) -> None:
        unlink_tag_url = f"https://{self.pricer_store_identifier}.{self.pricer_tenant_name}.pcm.pricer-plaza.com/api/public/core/v1/labels/{pricer_tag_id}/links"

        with self._get_integration_connection()._egress_session(
            "pos_pricer"
        ) as requests_session:
            try:
                setup_requests_session(
                    requests_session,
                    self.pricer_login,
                    self.pricer_password,
                    self.auth_url,
                )
                response = requests_session.delete(
                    unlink_tag_url, timeout=PRICER_REQUESTS_TIMEOUT
                )
                response.raise_for_status()
                _logger.info(
                    "Succesfully unlinked products from Pricer tag %s at Pricer API URL: %s",
                    pricer_tag_id,
                    unlink_tag_url,
                )
            except requests.exceptions.RequestException as e:
                _logger.warning(
                    "Failed to unlink product from Pricer tag %s at Pricer API URL: %s: %s",
                    pricer_tag_id,
                    unlink_tag_url,
                    e,
                )
                raise UserError(
                    self.env._(
                        "Failed to unlink Pricer tag %(pricer_tag)s at API url %(api_url)s",
                        pricer_tag=pricer_tag_id,
                        api_url=unlink_tag_url,
                    )
                ) from e

    def action_button_update_pricer_tags(self) -> dict:
        updated = self._update_pricer_tags(update_all=False)

        message = (
            self.last_update_status_message
            if updated
            else self.env._(
                "Everything is already up to date with Pricer. No update needed."
            )
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": message,
                "type": "danger" if message.startswith(self.env._("Error")) else "info",
            },
        }

    def _update_pricer_tags(self, update_all):
        anything_to_update = False

        for store in self:
            products = store.product_ids.filtered("pricer_product_to_create_or_update")
            tags = products.pricer_tag_ids.filtered("pricer_product_to_link")

            if not products and not tags:
                continue

            anything_to_update = True

            with store._get_integration_connection()._egress_session(
                "pos_pricer"
            ) as requests_session:
                try:
                    setup_requests_session(
                        requests_session,
                        store.pricer_login,
                        store.pricer_password,
                        store.auth_url,
                    )
                    if products:
                        requests_session.patch(
                            store.create_or_update_products_url,
                            json=[
                                p._acquire_pricer_product_payload() for p in products
                            ],
                            timeout=PRICER_REQUESTS_TIMEOUT,
                        ).raise_for_status()
                        products.write({"pricer_product_to_create_or_update": False})
                        _logger.info(
                            "Successfully created/updated products information for %s at Pricer API url: %s",
                            store.name,
                            store.create_or_update_products_url,
                        )
                    if tags:
                        requests_session.patch(
                            store.link_tags_url,
                            json=[t._get_link_body() for t in tags],
                            timeout=PRICER_REQUESTS_TIMEOUT,
                        ).raise_for_status()
                        tags.write({"pricer_product_to_link": False})
                        _logger.info(
                            "Successfully linked Pricer labels to products for %s at Pricer API URL: %s",
                            store.name,
                            store.link_tags_url,
                        )
                    store.last_update_status_message = self.env._(
                        "Update successfully sent to Pricer"
                    )

                except requests.exceptions.RequestException as e:
                    _logger.warning(e)
                    if e.response:
                        store.last_update_status_message = self.env._(
                            "Error: %(code)s - %(reason)s",
                            code=e.response.status_code,
                            reason=e.response.reason,
                        )
                    else:
                        store.last_update_status_message = self.env._(
                            "Error: check Pricer credentials"
                        )
                finally:
                    store.last_update_datetime = fields.Datetime.now()

        return anything_to_update
