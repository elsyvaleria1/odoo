import logging
import math
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools import frozendict

from odoo.addons.account.tools.tax_prices import price_from_tax_included_total
from odoo.addons.product.tools.product_matching import get_or_create_matching_product
from odoo.addons.sale_shopee import const, utils

if TYPE_CHECKING:
    from .shopee_item import ShopeeItem
    from odoo.addons.product.models.product_product import ProductProduct

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class ShopeeShop(models.Model):
    _name = "shopee.shop"
    _inherit = ["mixin.credential.holder"]
    _description = "Shopee Shop"
    _credential_holder_field = "shop_credential_id"
    _credential_purpose = "sale_shopee:shop"
    _CREDENTIAL_FIELDS = {
        "access_token": "access_token",
        "refresh_token": "refresh_token",
    }
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=True),
        }
    )

    name = fields.Char(required=True)
    account_id = fields.Many2one(
        comodel_name="shopee.account",
        string="Shopee Account",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    shopee_item_ids = fields.One2many(
        comodel_name="shopee.item",
        inverse_name="shop_id",
        string="Shopee Items",
    )

    shop_identifier = fields.Integer(
        string="Shopee Shop ID",
        readonly=True,
        required=True,
    )
    shop_credential_id = fields.Many2one(
        comodel_name="credential.credential",
        string="Credential",
        copy=False,
        ondelete="restrict",
        groups="base.group_system",
        help="Holds this shop's Shopee tokens.",
    )
    access_token = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        readonly=True,
        help="Access Token expires in 4 hours and is used to access the Shopee API.",
    )
    access_token_expiration_date = fields.Datetime(
        readonly=True,
        help="Access token expiration date. Computed using the expires_in returned by Shopee.",
    )
    refresh_token = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        readonly=True,
        help="Refresh Token is used to request a new Access Token and expires in 30 days. Once"
        " expired, the user must re-authorize the connection on Shopee Account view.",
    )
    authorization_expiration_date = fields.Datetime(
        readonly=True,
        help="Expiration Date of Authorization of a shop, that was returned during the Shopee shop"
        " authorization on Shopee Account view. Once expired, the user must re-authorize the"
        " connection on Shopee Account view.",
    )

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Default Salesperson",
        default=lambda self: self.env.user,
        check_company=True,
        help="The default salesperson assigned to Shopee orders",
    )
    team_id = fields.Many2one(
        comodel_name="team.team",
        string="Default Sales Team",
        domain=[("use_sale", "=", True)],
        check_company=True,
        help="The default Sales Team assigned to Shopee orders for reporting",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        readonly=True,
        required=True,
    )
    fbs_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="FBS Stock Location",
        domain="[('usage', '=', 'internal')]",
        check_company=True,
        help="The stock location managed by Shopee under the Fulfilled by Shopee (FBS) program.",
    )
    active = fields.Boolean(
        default=True,
        required=True,
        help="If made inactive, this account will no longer be synchronized with Shopee.",
    )
    status = fields.Selection(
        selection=[
            ("inactive", "Inactive"),
            ("active", "Active"),
            ("error", "Error"),
        ],
        default="inactive",
        readonly=True,
        help="The shop status on Shopee."
        "- Inactive: The shop is not yet approved by Shopee."
        "- Active: The shop is active and can be synchronized with Odoo."
        "- Error: The shop is banned and cannot be synchronized with Odoo.",
    )
    last_shop_status_sync_date = fields.Datetime(
        string="Last Shop Status Synchronization Date",
        default=fields.Datetime.now,
        required=True,
        help="The last time the shop status was synchronized with Shopee",
    )
    last_orders_sync_date = fields.Datetime(
        string="Last Order Synchronization Date",
        default=fields.Datetime.now,
        required=True,
        help="The last time the orders were synchronized with Shopee. Orders whose status has "
        "not changed since this date will not be created nor updated in Odoo.",
    )
    synchronize_inventory = fields.Boolean(
        default=False,
        help="Whether the available quantities of products linked to this shop are  synchronized"
        " with Shopee. Only products available in FBM or hybrid will be synchronized.",
    )

    order_count = fields.Integer(compute="_compute_order_count")
    shopee_item_count = fields.Count(count_of="shopee_item_ids")
    authorization_remaining_days = fields.Integer(
        compute="_compute_authorization_remaining_days",
        readonly=True,
        help="Remaining days of the shop authorization. Show a warning in the Shopee Shop view "
        "that the authorization will expire soon.",
    )

    def _compute_order_count(self) -> None:
        for shop in self:
            order_count = self.env["sale.order"].search_count(
                [("shopee_shop_id", "in", shop.ids)]
            )
            shop.order_count = order_count

    @api.depends("authorization_expiration_date")
    def _compute_authorization_remaining_days(self) -> None:
        for shop in self:
            if shop.authorization_expiration_date:
                shop.authorization_remaining_days = (
                    shop.authorization_expiration_date - fields.Datetime.now()
                ).days
            else:
                shop.authorization_remaining_days = -1

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company_id = vals.get("company_id") or self.env.company.id
            parent_warehouse = self.env["stock.warehouse"].search_read(
                self.env["stock.warehouse"]._get_domain_company_compatible(company_id),
                ["view_location_id"],
                limit=1,
            )
            location_name = self.env._(
                "Shopee Warehouse - %(shop)s", shop=vals.get("name")
            )
            if parent_warehouse:
                location = self.env["stock.location"].search(
                    [
                        *self.env["stock.location"]._get_domain_company_compatible(
                            company_id
                        ),
                        ("name", "=", location_name),
                        (
                            "location_id",
                            "=",
                            parent_warehouse[0]["view_location_id"][0],
                        ),
                    ],
                    limit=1,
                )
                if not location:
                    location = self.env["stock.location"].create(
                        {
                            "name": location_name,
                            "usage": "internal",
                            "location_id": parent_warehouse[0]["view_location_id"][0],
                            "company_id": company_id,
                        }
                    )
                vals["fbs_location_id"] = location.id

        return super().create(vals_list)

    def write(self, vals):
        if "company_id" in vals:
            raise UserError(
                self.env._("Changing the company of a Shopee shop is not allowed.")
            )
        return super().write(vals)

    def action_sync_orders(self) -> dict | None:
        self._sync_orders()
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def action_sync_pickings(self):
        return self.env["stock.picking"]._sync_shopee_pickings(tuple(self.ids))

    def action_sync_inventory(self):
        self._sync_inventory()

    def action_force_update_shop(self):
        return self._update_shop_information(force_update=True)

    def action_view_orders(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Sale Orders"),
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("shopee_shop_id", "=", self.id)],
        }

    def action_view_shopee_items(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Shopee Items"),
            "res_model": "shopee.item",
            "view_mode": "list,form",
            "domain": [("shop_id", "=", self.id)],
            "context": {"default_shop_id": self.id},
        }

    def action_archive(self):
        for shop in self:
            shop._reset_tokens()
        return super().action_archive()

    def create_or_update_shop(self, company_id, account_id, shop_id, shop_vals):
        shop = self.search(
            [("shop_identifier", "=", shop_id), ("account_id", "=", account_id)],
            limit=1,
        )

        if not shop:
            shop = self.create(
                {
                    "name": self.env._("Shopee Shop #%(shop_id)s", shop_id=shop_id),
                    "shop_identifier": shop_id,
                    "account_id": account_id,
                    "company_id": company_id,
                    **shop_vals,
                }
            )
        else:
            if shop_vals:
                shop.write(shop_vals)
            utils.request_access_token(shop)

        shop._update_shop_information(force_update=True)
        return shop

    def _update_shop_information(self, force_update=False):
        self.check_singleton()

        task_begin_datetime = fields.Datetime.now()
        if (
            force_update
            or not self.authorization_expiration_date
            or not self.last_shop_status_sync_date
            or self.last_shop_status_sync_date < task_begin_datetime - timedelta(days=1)
        ):
            shop_data = utils.send_shopee_api_request(self, "get_shop_info")
            expiration_date = datetime.fromtimestamp(shop_data["expire_time"])
            self.update(
                {
                    "status": const.SHOP_STATUS_MAPPING.get(
                        shop_data["status"], "error"
                    ),
                    "authorization_expiration_date": expiration_date,
                    "last_shop_status_sync_date": task_begin_datetime,
                }
            )

        return self

    def _sync_orders(self, auto_commit=True) -> None:
        shops = self or self.search([])
        _debug.pipeline("orders_sync_started", shops=shops, auto_commit=auto_commit)
        for shop in shops:
            shop._update_shop_information()
            if shop.status != "active":
                _debug.logic("shop_skipped", shop=shop, status=shop.status)
                continue

            start_sync_dt = fields.Datetime.now()

            try:
                while shop.last_orders_sync_date < start_sync_dt:
                    status_update_lower_limit = shop.last_orders_sync_date
                    status_update_upper_limit = min(
                        status_update_lower_limit
                        + timedelta(days=const.ORDER_LIST_DAYS_LIMIT),
                        start_sync_dt,
                    )
                    order_list = shop._get_order_list(
                        time_from=status_update_lower_limit,
                        time_to=status_update_upper_limit,
                    )
                    _debug.pipeline("batch_pulled", shop=shop, orders=len(order_list))
                    if not order_list:
                        shop.last_orders_sync_date = status_update_upper_limit
                        continue

                    orders_detail = shop._get_orders_detail(order_list)
                    upper_limit_timestamp = int(status_update_upper_limit.timestamp())
                    valid_orders_detail = [
                        od
                        for od in orders_detail
                        if od["update_time"] <= upper_limit_timestamp
                    ]
                    _debug.logic(
                        "batch_filtered",
                        pulled=len(orders_detail),
                        kept=len(valid_orders_detail),
                    )
                    if not valid_orders_detail:
                        shop.last_orders_sync_date = status_update_upper_limit
                        continue

                    for order_data in valid_orders_detail:
                        try:
                            if auto_commit:
                                with self.env.cr.savepoint():
                                    shop._process_order_data(order_data)
                            else:
                                shop._process_order_data(order_data)
                        except utils.ShopeeRateLimitError:
                            raise
                        except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                            shopee_order_ref = order_data["order_sn"]
                            _logger.info(
                                "A concurrency error occurred while processing the order data "
                                "with shopee_order_ref %(order_ref)s for Shopee shop id %(id)s."
                                " Discarding the error to trigger the retry mechanism.",
                                {"order_ref": shopee_order_ref, "id": shop.id},
                            )
                            raise
                        except Exception:
                            shopee_order_ref = order_data["order_sn"]
                            _logger.warning(
                                "A business error occurred while processing the order data"
                                " with shopee_order_ref %(order_ref)s for Shopee shop %(shop)s."
                                " Skipping the order data and moving to the next order.",
                                {"order_ref": shopee_order_ref, "shop": shop.id},
                                exc_info=True,
                            )
                            _debug.logic(
                                "order_data_skipped",
                                ref=shopee_order_ref,
                                reason="business_error",
                            )
                            self.env.cr.rollback()
                            shop._handle_sync_failure(
                                flow="order_sync", shopee_order_ref=shopee_order_ref
                            )
                            continue

                        if auto_commit:
                            self.env["ir.cron"]._commit_progress(processed=1)

                    valid_update_times = [
                        order["update_time"] for order in valid_orders_detail
                    ]
                    if (
                        valid_update_times
                        and len(orders_detail) == const.ORDER_DETAIL_SIZE_LIMIT
                    ):
                        shop.last_orders_sync_date = datetime.fromtimestamp(
                            max(valid_update_times)
                        )
                    else:
                        shop.last_orders_sync_date = status_update_upper_limit

            except utils.ShopeeRateLimitError as error:
                _debug.logic("sync_interrupted", shop=shop, op=error.operation)
                _logger.info(
                    "Rate limit reached while synchronizing sales orders for Shopee account with"
                    " id %(account)d. Operation: %(error_operation)s",
                    {"account": shop.account_id.id, "error_operation": error.operation},
                )
                continue

    def _get_order_list(self, time_from, time_to) -> dict | list:
        response = utils.send_shopee_api_request(
            self,
            "get_order_list",
            {
                "time_range_field": "update_time",
                "time_from": int(time_from.timestamp()),
                "time_to": int(time_to.timestamp()),
                "page_size": const.ORDER_LIST_SIZE_LIMIT,
                "cursor": 0,
            },
        )
        return [order["order_sn"] for order in response["order_list"] or []]

    def _get_orders_detail(self, order_sn_list):
        batches = [
            order_sn_list[i : i + const.ORDER_DETAIL_SIZE_LIMIT]
            for i in range(0, len(order_sn_list), const.ORDER_DETAIL_SIZE_LIMIT)
        ]
        fields_to_fetch = [
            "buyer_user_id",
            "buyer_username",
            "estimated_shipping_fee",
            "recipient_address",
            "actual_shipping_fee",
            "item_list",
            "actual_shipping_fee_confirmed",
            "fulfillment_flag",
            "package_list",
            "shipping_carrier",
            "total_amount",
        ]
        fields_to_fetch = ",".join(fields_to_fetch)
        orders_detail = []
        for batch in batches:
            response = utils.send_shopee_api_request(
                self,
                "get_order_detail",
                {
                    "order_sn_list": ",".join(batch),
                    "response_optional_fields": fields_to_fetch,
                },
            )
            orders_detail += response.get("order_list", [])

        return orders_detail

    def _process_order_data(self, order_data):
        self.check_singleton()

        shopee_order_ref = order_data["order_sn"]
        shopee_status = order_data["order_status"]
        order = self.env["sale.order"].search(
            [
                ("shopee_order_ref", "=", shopee_order_ref),
                ("shopee_shop_id", "=", self.id),
            ],
            limit=1,
        )
        fulfillment_type = const.FULFILLMENT_TYPE_MAPPING[
            order_data["fulfillment_flag"]
        ]
        if not order:
            if shopee_status in const.ORDER_STATUSES_TO_SYNC[fulfillment_type]:
                order = self._create_order_from_data(order_data)
                if order.shopee_fulfillment_type == "fbs":
                    self._create_stock_moves(order)
                elif order.shopee_fulfillment_type in ["fbm", "hybrid"]:
                    order.with_context(mail_notrack=True).action_lock()
                _debug.lifecycle("shopee_order_created", order=order)
                _logger.info(
                    "Created a new sales order with shopee_order_ref %(ref)s for Shopee shop"
                    " with id %(id)s.",
                    {"ref": shopee_order_ref, "id": self.id},
                )
            else:
                _debug.logic("shopee_order_ignored", status=shopee_status)
                _logger.info(
                    "Ignored Shopee order with reference %(ref)s and status %(status)s for Shopee"
                    " shop with id %(id)s.",
                    {"ref": shopee_order_ref, "status": shopee_status, "id": self.id},
                )
        elif shopee_status == "CANCELLED" and order.state != "cancel":
            _debug.lifecycle("shopee_order_cancelled", order=order)
            order._action_cancel()
            _logger.info(
                "Cancelled sales order with shopee_order_ref %(ref)s for Shopee shop with id"
                " %(id)s.",
                {"ref": shopee_order_ref, "id": self.id},
            )
        elif shopee_status in ("SHIPPED", "COMPLETED") and fulfillment_type != "fbs":
            valid_picks = order.picking_ids.filtered(
                lambda pick: pick.state != "cancel"
            )
            not_stored_label = valid_picks.filtered(
                lambda p: p.shopee_label_status != "stored"
            )
            _debug.logic("labels_forced_stored", forced=len(not_stored_label))
            if not_stored_label:
                not_stored_label.shopee_label_status = "stored"
                _logger.info(
                    "Forced label to be stored for sales order with Shopee order"
                    " reference %(ref)s and Shopee shop with id %(id)s.",
                    {"ref": shopee_order_ref, "id": self.id},
                )
        else:
            _debug.logic("shopee_order_unchanged", status=shopee_status)
            _logger.info(
                "Ignored already synchronized sales order with shopee_order_ref %(ref)s for"
                " Shopee shop with id %(id)s.",
                {"ref": shopee_order_ref, "id": self.id},
            )

        _debug.lifecycle("delivery_status_set", order=order, status=shopee_status)
        order.shopee_delivery_status = const.DELIVERY_STATUS_MAPPING.get(
            shopee_status, "error"
        )
        return order

    def _create_order_from_data(self, order_data):
        shipping_code = order_data["shipping_carrier"]
        shipping_product = self._get_or_create_matching_product(
            shipping_code, "default_shipping_product", "Shopee Shipping", "service"
        )
        currency = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([("name", "=", order_data["currency"])], limit=1)
        )
        shopee_order_ref = order_data["order_sn"]
        contact_partner, delivery_partner = self._get_or_create_partners_from_data(
            order_data
        )
        fiscal_position = (
            self.env["account.fiscal.position"]
            .with_company(self.company_id)
            ._get_fiscal_position(contact_partner, delivery_partner)
        )
        order_lines_values = self._prepare_order_lines_values(
            order_data, currency, fiscal_position, shipping_product
        )
        fulfillment_type = order_data["fulfillment_flag"]
        order_lines = [
            Command.create(order_line_values)
            for order_line_values in order_lines_values
        ]
        origin = self.env._(
            "Shopee Order %(shopee_order_ref)s at %(shop_name)s",
            shopee_order_ref=shopee_order_ref,
            shop_name=self.name,
        )
        delivery_status = const.DELIVERY_STATUS_MAPPING.get(
            order_data["order_status"], "draft"
        )
        order_vals = {
            "origin": origin,
            "state": "done",
            "locked": fulfillment_type == "fulfilled_by_shopee",
            "date_order": datetime.fromtimestamp(order_data["create_time"]),
            "partner_id": contact_partner.id,
            "pricelist_id": self._get_or_create_pricelist(currency).id,
            "line_ids": order_lines,
            "partner_shipping_id": delivery_partner.id,
            "require_signature": False,
            "require_payment": False,
            "fiscal_position_id": fiscal_position.id,
            "company_id": self.company_id.id,
            "user_id": self.user_id.id,
            "team_id": self.team_id.id,
            "shopee_order_ref": shopee_order_ref,
            "shopee_shop_id": self.id,
            "shopee_fulfillment_type": const.FULFILLMENT_TYPE_MAPPING[fulfillment_type],
            "shopee_delivery_status": delivery_status,
        }
        if (
            fulfillment_type == "fulfilled_by_shopee"
            and self.fbs_location_id.warehouse_id
        ):
            order_vals["warehouse_id"] = self.fbs_location_id.warehouse_id.id
        order = (
            self.env["sale.order"]
            .with_context(mail_create_nosubscribe=True)
            .with_company(self.company_id)
            .create(order_vals)
        )

        if order.picking_ids and shipping_code:
            delivery_method = self._get_or_create_delivery_carrier(
                shipping_code, shipping_product
            )
            order.picking_ids.carrier_id = delivery_method
        return order

    def _get_or_create_matching_product(
        self,
        internal_reference: str,
        default_xmlid: str,
        default_name: str,
        default_type: str,
        fallback: bool = True,
    ) -> ProductProduct:
        self.check_singleton()
        return get_or_create_matching_product(
            self.env,
            self.company_id,
            internal_reference,
            f"sale_shopee.{default_xmlid}",
            lambda: self.env["product.product"]._restore_shopee_data_product(
                default_name, default_type, default_xmlid
            ),
            fallback=fallback,
        )

    def _get_or_create_partners_from_data(self, order_data) -> tuple:

        def get_streets_from_full_address(address_):
            blocks_ = address_.get("full_address").split(", ")
            for key, value in address_.items():
                if key in ["city", "state", "region", "zipcode"] and value in blocks_:
                    blocks_.remove(value)
            middle_index_ = math.ceil(len(blocks_) / 2)
            street_ = ", ".join(blocks_[:middle_index_])
            street2_ = ", ".join(blocks_[middle_index_:])
            return street_, street2_ or False

        self.check_singleton()

        shopee_order_ref = order_data["order_sn"]
        shopee_buyer_identifier = order_data["buyer_user_id"]
        buyer_name = order_data["buyer_username"]
        shipping_address_name = order_data["recipient_address"]["name"]
        city = order_data["recipient_address"]["city"]
        street, street2 = get_streets_from_full_address(order_data["recipient_address"])
        zip_code = order_data["recipient_address"]["zipcode"]
        country_code = order_data["recipient_address"]["region"]
        state_name = order_data["recipient_address"]["state"]
        phone = order_data["recipient_address"]["phone"]
        country = self.env["res.country"].search([("code", "=", country_code)], limit=1)
        state = self.env["res.country.state"]
        if country and state_name:
            state = self.env["res.country.state"].search(
                [
                    (
                        "name",
                        "=ilike",
                        state_name,
                    ),
                    ("country_id", "=", country.id),
                ],
                limit=1,
            )
        partner_vals = {
            "street": street,
            "street2": street2,
            "zip": zip_code,
            "city": city,
            "country_id": country.id if country else False,
            "state_id": state.id if state else False,
            "phone_ids": [Command.create({"number": phone, "type": "landline"})]
            if phone
            else False,
            "customer_rank": 1,
            "company_id": self.company_id.id,
            "shopee_buyer_identifier": shopee_buyer_identifier,
        }

        contact = (
            self.env["res.partner"].search(
                [
                    *self.env["product.pricelist"]._get_domain_company_compatible(
                        self.company_id
                    ),
                    ("type", "=", "contact"),
                    ("name", "=", buyer_name),
                    ("shopee_buyer_identifier", "=", shopee_buyer_identifier),
                ],
                limit=1,
            )
            if shopee_buyer_identifier
            else None
        )
        if not contact:
            contact_name = buyer_name or self.env._(
                "Shopee Customer #%(order_no)s", order_no=shopee_order_ref
            )
            contact = (
                self.env["res.partner"]
                .with_context(tracking_disable=True)
                .create(
                    {
                        "name": contact_name,
                        **partner_vals,
                    }
                )
            )

        delivery = (
            contact
            if (
                contact.name == shipping_address_name
                and contact.street == street
                and contact.street2 == street2
                and contact.zip == zip_code
                and contact.city == city
                and contact.country_id.id == country.id
                and contact.state_id.id == state.id
            )
            else None
        )
        if not delivery:
            delivery = self.env["res.partner"].search(
                [
                    *self.env["res.partner"]._get_domain_company_compatible(
                        self.company_id
                    ),
                    ("type", "=", "delivery"),
                    ("parent_id", "=", contact.id),
                    ("name", "=", shipping_address_name),
                    ("street", "=", street),
                    ("street2", "=", street2),
                    ("zip", "=", zip_code),
                    ("city", "=", city),
                    ("country_id", "=", country.id),
                    ("state_id", "=", state.id),
                ],
                limit=1,
            )
        if not delivery:
            delivery = (
                self.env["res.partner"]
                .with_context(tracking_disable=True)
                .create(
                    {
                        "name": shipping_address_name,
                        "type": "delivery",
                        "parent_id": contact.id,
                        **partner_vals,
                    }
                )
            )

        return contact, delivery

    def _prepare_order_lines_values(
        self, order_data, currency, fiscal_pos, shipping_product
    ):
        self.check_singleton()

        order_lines_values = []
        for item_data in order_data["item_list"]:
            sku = item_data["item_sku"] or item_data["model_sku"]
            fulfillment_type = const.FULFILLMENT_TYPE_MAPPING[
                order_data["fulfillment_flag"]
            ]
            shopee_item = self._acquire_item(
                sku, item_data["item_id"], item_data["model_id"], fulfillment_type
            )
            product_taxes = shopee_item.product_id.taxes_id._filter_taxes_by_company(
                self.company_id
            )
            promotion_type = self._get_promotion_type(item_data.get("promotion_type"))
            promotion_id = item_data.get("promotion_id")
            if not promotion_id:
                description = self.env._(
                    "[%(sku)s] %(product_name)s",
                    sku=sku,
                    product_name=item_data["item_name"],
                )
            else:
                item_title = item_data["item_name"]
                description = self.env._(
                    "[%(sku)s] %(product_title)s\nPromotion: %(promotion_type)s - id: "
                    "%(promotion_id)d",
                    sku=sku,
                    product_title=item_title,
                    promotion_type=promotion_type,
                    promotion_id=promotion_id,
                )
            quantity = item_data["model_quantity_purchased"]
            original_subtotal = quantity * item_data["model_original_price"]
            discounted_subtotal = quantity * item_data["model_discounted_price"]

            taxes = fiscal_pos.map_tax(product_taxes)
            subtotal = self._get_price_from_tax_included_total(
                discounted_subtotal, taxes, currency
            )
            order_lines_values.append(
                self._convert_to_order_line_values(
                    product_id=shopee_item.product_id.id,
                    description=description,
                    tax_ids=taxes.ids,
                    original_subtotal=original_subtotal,
                    subtotal=subtotal,
                    quantity=quantity,
                )
            )

        return order_lines_values

    def _acquire_item(
        self,
        sku: str,
        item_identifier: str | int,
        model_identifier: str | int,
        fulfillment_type: str = "fbm",
    ) -> ShopeeItem:
        self.check_singleton()
        sync_to_shopee = fulfillment_type in ["fbm", "hybrid"]
        shopee_item = self.shopee_item_ids.filtered(
            lambda i: i.shopee_item_identifier == str(item_identifier)
        )
        if model_identifier:
            shopee_item = shopee_item.filtered(
                lambda i: i.shopee_model_identifier == str(model_identifier)
            )
        if not shopee_item:
            shopee_item = (
                self.env["shopee.item"]
                .with_context(tracking_disable=True)
                .create(
                    {
                        "product_id": self._get_or_create_matching_product(
                            sku, "default_sale_product", "Shopee Sales", "consu"
                        ).id,
                        "shop_id": self.id,
                        "shopee_item_identifier": item_identifier,
                        "shopee_model_identifier": model_identifier,
                        "sync_to_shopee": sync_to_shopee,
                    }
                )
            )
        elif (
            "sale_shopee.default_sale_product"
            in shopee_item.product_id._get_external_ids().get(
                shopee_item.product_id.id, []
            )
        ):
            product = self._get_or_create_matching_product(
                sku, "", "", "", fallback=False
            )
            if product:
                shopee_item.product_id = product.id

        return shopee_item

    def _get_promotion_type(self, promotion_type):
        promotion_type_mapping = {
            "product_promotion": self.env._("Product Promotion"),
            "flash_sale": self.env._("Flash Sale"),
            "bundle_deal": self.env._("Bundle Deal"),
            "add_on_deal_main": self.env._("Add-on Deal Main"),
            "add_on_deal_sub": self.env._("Add-on Deal Sub"),
        }
        return promotion_type_mapping.get(
            promotion_type, self.env._("Unknown Promotion Type")
        )

    def _get_price_from_tax_included_total(self, total, taxes, currency):
        return price_from_tax_included_total(total, taxes, currency)

    def _convert_to_order_line_values(self, **kwargs) -> dict:
        subtotal = kwargs.get("subtotal", 0)
        quantity = kwargs.get("quantity", 1)
        original_subtotal = kwargs.get("original_subtotal", 0) or subtotal
        diff = original_subtotal - subtotal
        tax_ids = kwargs.get("tax_ids")
        return {
            "name": kwargs.get("description", ""),
            "product_id": kwargs.get("product_id"),
            "price_unit": original_subtotal / quantity if quantity else 0,
            "tax_ids": tax_ids or [],
            "product_qty": quantity,
            "discount": diff / original_subtotal * 100 if original_subtotal else 0,
        }

    def _get_or_create_pricelist(self, currency):
        self.check_singleton()
        pricelist = (
            self.env["product.pricelist"]
            .with_context(active_test=False)
            .search(
                [
                    *self.env["product.pricelist"]._get_domain_company_compatible(
                        self.company_id
                    ),
                    ("currency_id", "=", currency.id),
                ],
                limit=1,
            )
        )
        if not pricelist:
            pricelist = (
                self.env["product.pricelist"]
                .with_context(tracking_disable=True)
                .create(
                    {
                        "name": self.env._(
                            "Shopee Pricelist %(currency)s", currency=currency.name
                        ),
                        "active": False,
                        "currency_id": currency.id,
                        "company_id": self.company_id.id,
                    }
                )
            )
        return pricelist

    def _get_or_create_delivery_carrier(self, shipping_code, shipping_product):
        delivery_method = self.env["delivery.carrier"].search(
            [("name", "=", shipping_code)],
            limit=1,
        )
        if not delivery_method:
            delivery_method = self.env["delivery.carrier"].create(
                {"name": shipping_code, "product_id": shipping_product.id}
            )
        return delivery_method

    def _create_stock_moves(self, order):
        customers_location = self.env.ref("stock.stock_location_customers")
        for order_line in order.line_ids.filtered(
            lambda l: l.product_id.type == "consu"
        ):
            stock_move = self.env["stock.move"].create(
                {
                    "company_id": self.company_id.id,
                    "product_id": order_line.product_id.id,
                    "product_uom_qty": order_line.product_qty,
                    "product_uom_id": order_line.product_uom_id.id,
                    "location_id": self.fbs_location_id.id,
                    "location_dest_id": customers_location.id,
                    "state": "confirmed",
                    "sale_line_id": order_line.id,
                }
            )
            stock_move._update_quantity_done(order_line.product_qty)
            stock_move.picked = True
            stock_move._action_done()

    def _handle_sync_failure(
        self, flow="", shopee_order_ref=False, error_messages=False
    ) -> None:
        if flow == "order_sync":
            _logger.error(
                "Failed to synchronize order with shopee reference %(ref)s for shopee.shop with "
                "id %(shop_id)s (Shope Name: %(shop_name)s)."
                "Please create the order manually.",
                {"ref": shopee_order_ref, "shop_id": self.id, "shop_name": self.name},
            )
            mail_template_id = "sale_shopee.order_sync_failure"
        elif flow == "inventory_sync":
            _logger.error(
                "Failed to synchronize the inventory for items in shopee.shop with id "
                "%(shop_id)s (Shope Name: %(shop_name)s).",
                {"shop_id": self.id, "shop_name": self.name},
            )
            mail_template_id = "sale_shopee.inventory_sync_failure"
        else:
            _logger.error(
                "Failed to synchronize pickings for shopee.shop with id "
                "%(shop_id)s (Shope Name: %(shop_name)s).",
                {"shop_id": self.id, "shop_name": self.name},
            )
            mail_template_id = "sale_shopee.picking_sync_failure"

        mail_template = self.env.ref(mail_template_id, raise_if_not_found=False)
        if not mail_template:
            _logger.warning(
                "The mail template with xmlid %(mail_template)s has been deleted.",
                {"mail_template": mail_template_id},
            )
        else:
            responsible_emails = {
                user.email
                for user in filter(
                    None,
                    (
                        self.user_id,
                        self.env.ref("base.user_admin", raise_if_not_found=False),
                    ),
                )
            }
            mail_template.with_context(
                email_to=",".join(responsible_emails),
                shopee_order_ref=shopee_order_ref,
                error_messages=error_messages,
                shopee_shop=self.name,
            ).send_mail(self.env.user.id)
            _logger.info(
                "Sent synchronization failure notification email to %(emails)s",
                {"emails": ", ".join(responsible_emails)},
            )

    def _sync_inventory(self, auto_commit=True) -> None:
        shops = self or self.search([])
        for shop in shops:
            shop._update_shop_information()
            if shop.status != "active" or not shop.synchronize_inventory:
                continue
            shop.shopee_item_ids._sync_inventory(auto_commit)

    def _reset_tokens(self) -> None:
        self.update(
            {
                "access_token": False,
                "access_token_expiration_date": False,
                "refresh_token": False,
                "authorization_expiration_date": False,
            }
        )
