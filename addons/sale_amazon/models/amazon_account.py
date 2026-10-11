import logging
from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlencode as url_encode

import dateutil.parser
from markupsafe import Markup

from odoo import Command, api, exceptions, fields, models, modules
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY as CONCURRENCY_ERRORS
from odoo.tools import frozendict, urls

from odoo.addons.account.tools.tax_prices import price_from_tax_included_total
from odoo.addons.sale_amazon import const
from odoo.addons.sale_amazon import utils as amazon_utils
from odoo.addons.sale_amazon.controllers.onboarding import issue_oauth_state

if TYPE_CHECKING:
    from odoo.addons.product.models.product_product import ProductProduct
    from odoo.addons.sale_amazon.models.amazon_marketplace import AmazonMarketplace
    from odoo.addons.sale_amazon.models.amazon_offer import AmazonOffer

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class AmazonAccount(models.Model):
    _name = "amazon.account"
    _description = "Amazon Account"
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=True),
        }
    )

    name = fields.Char(
        compute="_compute_name",
        store=True,
        readonly=False,
        required=True,
        help="The user-defined name of the account.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        readonly=True,
        required=True,
    )
    offer_ids = fields.One2many(
        comodel_name="amazon.offer",
        inverse_name="account_id",
        string="Offers",
        bypass_search_access=True,
    )
    base_marketplace_id = fields.Many2one(
        comodel_name="amazon.marketplace",
        string="Home Marketplace",
        required=True,
        help="The home marketplace of this account; used for authentication only.",
    )
    available_marketplace_ids = fields.Many2many(
        comodel_name="amazon.marketplace",
        relation="amazon_account_marketplace_rel",
        string="Available Marketplaces",
        copy=False,
        help="The marketplaces this account has access to.",
    )
    active_marketplace_ids = fields.Many2many(
        comodel_name="amazon.marketplace",
        relation="amazon_account_active_marketplace_rel",
        string="Marketplaces",
        copy=False,
        domain='[("id", "in", available_marketplace_ids)]',
        help="The marketplaces this account sells on.",
    )
    default_product_ids = fields.Many2many(
        comodel_name="product.product",
        string="Default Products",
        compute="_compute_default_product_ids",
        context={"active_test": False},
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Salesperson",
        default=lambda self: self.env.user,
        check_company=True,
    )
    team_id = fields.Many2one(
        comodel_name="team.team",
        string="Sales Team",
        domain=[("use_sale", "=", True)],
        check_company=True,
        help="The Sales Team assigned to Amazon orders for reporting",
    )
    location_id = fields.Many2one(
        comodel_name="stock.location",
        string="FBA Stock Location",
        domain='[("usage", "=", "internal")]',
        check_company=True,
        help="The location of the stock managed by Amazon under the Amazon Fulfillment program.",
    )
    synchronize_inventory = fields.Boolean(
        string="FBM Stock",
        default=True,
        help="Whether the available quantities of FBM products linked to this account are"
        " synchronized with Amazon.",
    )
    last_orders_sync = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
        help="The last synchronization date for orders placed on this account. Orders whose status"
        " has not changed since this date will not be created nor updated in Odoo.",
    )
    active = fields.Boolean(
        default=True,
        required=True,
        help="If made inactive, this account will no longer be synchronized with Amazon.",
    )

    seller_key = fields.Char()
    credential_id = fields.Many2one(
        comodel_name="credential.credential",
        copy=False,
        ondelete="restrict",
        groups="base.group_system",
        help="Holds this account's LWA refresh token.",
    )
    refresh_token = fields.Char(
        string="LWA Refresh Token",
        compute="_compute_refresh_token",
        inverse="_inverse_refresh_token",
        classification="secret.credential",
        groups="base.group_system",
        help="The long-lived token that can be exchanged for a new access token.",
    )
    access_token = fields.Char(
        string="LWA Access Token",
        store=False,
        help="The short-lived token used to query Amazon API on behalf of a seller.",
    )
    access_token_expiry = fields.Datetime(
        string="LWA Access Token Expiry",
        default="1970-01-01",
        store=False,
        help="The moment at which the token becomes invalid.",
    )
    restricted_data_token = fields.Char(
        store=False,
        help="The short-lived token used instead of the LWA Access Token to access restricted data",
    )
    restricted_data_token_expiry = fields.Datetime(
        default="1970-01-01",
        store=False,
        help="The moment at which the Restricted Data Token becomes invalid.",
    )

    state = fields.Selection(
        selection=[("disconnected", "Disconnected"), ("connected", "Connected")],
        compute="_compute_state",
    )
    offer_count = fields.Integer(compute="_compute_offer_count")
    order_count = fields.Integer(compute="_compute_order_count")


    @api.depends("base_marketplace_id")
    def _compute_name(self):
        for account in self:
            if account.base_marketplace_id:
                account.name = account.base_marketplace_id.name

    def _compute_default_product_ids(self) -> None:
        ProductProduct = self.env["product.product"]
        default_product = self.env.ref(
            "sale_amazon.default_product", raise_if_not_found=False
        ) or ProductProduct._restore_data_product(
            "Amazon Sales", "consu", "default_product"
        )
        shipping_product = self.env.ref(
            "sale_amazon.shipping_product", raise_if_not_found=False
        ) or ProductProduct._restore_data_product(
            "Amazon Shipping", "consu", "shipping_product"
        )
        for account in self:
            account.default_product_ids = default_product + shipping_product

    @api.depends("credential_id")
    def _compute_state(self):
        for account in self:
            account.state = (
                "connected" if account.sudo().credential_id else "disconnected"
            )

    @api.depends("credential_id")
    def _compute_refresh_token(self) -> None:
        for account in self:
            credential = account.credential_id.sudo()
            account.refresh_token = (
                credential
                and credential._use_secret_payload("sale_amazon:refresh_token").get(
                    "credential_value"
                )
            ) or False

    def _inverse_refresh_token(self) -> None:
        for account in self:
            account._amazon_store_refresh_token(account.refresh_token)

    def _amazon_store_refresh_token(self, value) -> None:
        self.check_singleton()
        credential = self.credential_id.sudo()
        if not value:
            if credential:
                self.credential_id = False
                credential.unlink()
            return
        if not credential:
            credential = (
                self.env["credential.credential"]
                .sudo()
                .create(
                    {
                        "name": self.env._(
                            "Amazon: %s", self.name or self.seller_key or self.id
                        ),
                        "category_id": self.env.ref(
                            "credential.credential_category_bearer_token"
                        ).id,
                        "company_id": self.company_id.id,
                        "credential_value": value,
                    }
                )
            )
            self.credential_id = credential.id
            return
        credential.credential_value = value

    def _compute_offer_count(self) -> None:
        offers_data = self.env["amazon.offer"]._read_group(
            [("account_id", "in", self.ids)], ["account_id"], ["__count"]
        )
        accounts_data = {account.id: count for account, count in offers_data}
        for account in self:
            account.offer_count = accounts_data.get(account.id, 0)

    def _compute_order_count(self) -> None:
        orders_per_offer = self.env["sale.order.line"]._read_group(
            [("amazon_offer_id.account_id", "in", self.ids)],
            groupby=["amazon_offer_id"],
            aggregates=["order_id:recordset"],
        )
        orders_per_account = defaultdict(lambda: self.env["sale.order"])
        for offer, orders in orders_per_offer:
            orders_per_account[offer.account_id] += orders
        for account in self:
            account.order_count = len(orders_per_account.get(account, []))


    @api.onchange("last_orders_sync")
    def _onchange_last_orders_sync(self) -> dict | None:
        self.check_singleton()
        if self._origin.id:
            return {
                "warning": {
                    "title": self.env._("Warning"),
                    "message": self.env._(
                        "If the date is set in the past, orders placed on this Amazon "
                        "Account before the first synchronization of the module might be "
                        "synchronized with Odoo.\n"
                        "If the date is set in the future, orders placed on this Amazon "
                        "Account between the previous and the new date will not be "
                        "synchronized with Odoo."
                    ),
                }
            }
        return None


    @api.constrains("active_marketplace_ids")
    def _check_actives_subset_of_availables(self) -> None:
        for account in self:
            if account.active_marketplace_ids - account.available_marketplace_ids:
                raise exceptions.ValidationError(
                    self.env._("Only available marketplaces can be selected")
                )


    @api.model_create_multi
    def create(self, vals_list):
        amazon_accounts_rg = self._read_group([], ["team_id", "location_id"])
        amazon_teams_ids = [team.id for team, __ in amazon_accounts_rg]
        amazon_locations_ids = [location.id for __, location in amazon_accounts_rg]
        for vals in vals_list:
            location = self.env["stock.location"].search(
                [
                    *self.env["stock.location"]._check_company_domain(
                        vals.get("company_id")
                    ),
                    ("id", "in", amazon_locations_ids),
                ],
                limit=1,
            )
            if not location:
                parent_location_data = self.env["stock.warehouse"].search_read(
                    [
                        *self.env["stock.warehouse"]._check_company_domain(
                            vals.get("company_id")
                        )
                    ],
                    ["view_location_id"],
                    limit=1,
                )
                location = self.env["stock.location"].create(
                    {
                        "name": "Amazon",
                        "usage": "internal",
                        "location_id": parent_location_data[0]["view_location_id"][0]
                        if parent_location_data
                        else False,
                        "company_id": vals.get("company_id"),
                    }
                )
            vals.update({"location_id": location.id})

            team = self.env["team.team"].search(
                [
                    *self.env["team.team"]._check_company_domain(
                        vals.get("company_id")
                    ),
                    ("id", "in", amazon_teams_ids),
                ],
                limit=1,
            )
            if not team:
                team = self.env["team.team"].create(
                    {
                        "use_sale": True,
                        "name": "Amazon",
                        "company_id": vals.get("company_id"),
                    }
                )
            vals.update({"team_id": team.id})

        _debug.lifecycle("amazon_account_create", rows=len(vals_list))
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_to_so(self) -> None:
        has_linked_so_line = self.env["sale.order.line"].search(
            [("amazon_offer_id.account_id", "in", self.ids)], limit=1
        )
        if has_linked_so_line:
            _debug.logic(
                "account_unlink_refused",
                accounts=self,
                reason="linked_sale_order_line",
                line=has_linked_so_line,
            )
            raise UserError(
                self.env._(
                    "You cannot delete an account that is linked to sale orders. Please archive it"
                    " instead."
                )
            )


    def action_archive(self):
        _debug.lifecycle("amazon_account_archived", accounts=self)
        for account in self:
            account.action_reset_refresh_token()
        return super().action_archive()

    def action_redirect_to_oauth_url(self) -> dict:
        self.check_singleton()

        base_seller_central_url = self.base_marketplace_id.seller_central_url
        oauth_url = urls.urljoin(base_seller_central_url, "/apps/authorize/consent")
        base_database_url = self.get_base_url()
        metadata = {
            "return_url": urls.urljoin(base_database_url, "amazon/return"),
            "token": issue_oauth_state(self),
        }
        oauth_url_params = {
            "application_id": const.APP_ID,
            "state": json_dumps(metadata),
        }
        return {
            "type": "ir.actions.act_url",
            "url": f"{oauth_url}?{url_encode(oauth_url_params)}",
            "target": "self",
        }

    def action_reset_refresh_token(self) -> None:
        self.check_singleton()

        self.sudo().refresh_token = False

    def action_update_available_marketplaces(self) -> dict:
        for account in self:
            available_marketplaces = account._get_available_marketplaces()
            new_marketplaces = (
                available_marketplaces - account.available_marketplace_ids
            )
            account.write(
                {"available_marketplace_ids": [Command.set(available_marketplaces.ids)]}
            )
            account.active_marketplace_ids &= account.available_marketplace_ids
            account.active_marketplace_ids += new_marketplaces
        return {
            "effect": {
                "type": "rainbow_man",
                "message": self.env._(
                    "Successfully updated the marketplaces available to this account!"
                ),
            }
        }

    def action_view_offers(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Offers"),
            "res_model": "amazon.offer",
            "view_mode": "list",
            "domain": [("account_id", "=", self.id)],
            "context": {"default_account_id": self.id},
        }

    def action_view_orders(self):
        self.check_singleton()
        order_lines = self.env["sale.order.line"].search(
            [
                ("amazon_offer_id", "!=", False),
                ("amazon_offer_id.account_id", "=", self.id),
            ]
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Orders"),
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("id", "in", order_lines.order_id.ids)],
            "context": {"create": False},
        }

    def action_sync_orders(self):
        self._sync_orders()

    def action_sync_pickings(self):
        self.env["stock.picking"]._sync_pickings(tuple(self.ids))

    def action_sync_inventory(self):
        self._sync_inventory()

    def action_sync_feeds_status(self) -> None:
        self._sync_feeds()

    def action_recover_order(self):
        self.check_singleton()
        return {
            "name": self.env._("Recover Order"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.amazon.account.sync.order",
            "target": "new",
        }


    def _get_available_marketplaces(self):
        self.check_singleton()

        amazon_utils.check_account_is_set_up(self, require_marketplaces=False)
        try:
            response_content = amazon_utils.send_sp_api_request(
                self, "getMarketplaceParticipations"
            )
        except amazon_utils.AmazonRateLimitError as err:
            _logger.info(
                "Rate limit reached while updating available marketplaces for Amazon account with "
                "id %s.",
                self.id,
            )
            raise UserError(
                self.env._(
                    "You reached the maximum number of requests for this operation; please try again "
                    "later."
                )
            ) from err
        else:
            available_marketplace_api_refs = [
                marketplace["marketplace"]["id"]
                for marketplace in response_content["payload"]
            ]
            return self.env["amazon.marketplace"].search(
                [("api_ref", "in", available_marketplace_api_refs)]
            )

    def _sync_orders(self, auto_commit=True) -> None:
        accounts = self or self.search([])
        _debug.pipeline(
            "orders_sync_started",
            accounts=accounts,
            called_on_recordset=bool(self),
            auto_commit=auto_commit,
        )
        for account in accounts:
            account = account[0]
            amazon_utils.check_account_is_set_up(account)

            last_updated_after = (
                account.last_orders_sync
            )
            status_update_upper_limit = None

            payload = {
                "LastUpdatedAfter": last_updated_after.isoformat(sep="T"),
                "MarketplaceIds": ",".join(
                    account.active_marketplace_ids.mapped("api_ref")
                ),
            }
            try:
                has_next_page = True
                while has_next_page:
                    orders_batch_data, has_next_page = amazon_utils.pull_batch_data(
                        account, "getOrders", payload
                    )
                    orders_data = orders_batch_data["Orders"]
                    status_update_upper_limit = dateutil.parser.parse(
                        orders_batch_data["LastUpdatedBefore"]
                    )
                    _debug.pipeline(
                        "orders_batch_pulled",
                        account=account,
                        orders=len(orders_data),
                        has_next_page=has_next_page,
                        since=last_updated_after,
                        until=status_update_upper_limit,
                    )

                    for order_data in orders_data:
                        try:
                            if auto_commit:
                                with self.env.cr.savepoint():
                                    account._process_order_data(order_data)
                            else:
                                account._process_order_data(order_data)
                        except amazon_utils.AmazonRateLimitError:
                            raise
                        except Exception as error:
                            if modules.module.current_test:
                                raise
                            amazon_order_ref = order_data["AmazonOrderId"]
                            if isinstance(error, CONCURRENCY_ERRORS):
                                _debug.logic(
                                    "order_data_retried",
                                    account=account,
                                    ref=amazon_order_ref,
                                    reason="concurrency_error",
                                    error=type(error).__name__,
                                )
                                _logger.info(
                                    "A concurrency error occurred while processing the order data "
                                    "with amazon_order_ref %s for Amazon account with id %s. "
                                    "Discarding the error to trigger the retry mechanism.",
                                    amazon_order_ref,
                                    account.id,
                                )
                                raise
                            _logger.warning(
                                "A business error occurred while processing the order data "
                                "with amazon_order_ref %s for Amazon account with id %s. "
                                "Skipping the order data and moving to the next order.",
                                amazon_order_ref,
                                account.id,
                                exc_info=True,
                            )
                            _debug.logic(
                                "order_data_skipped",
                                account=account,
                                ref=amazon_order_ref,
                                reason="business_error",
                                error=type(error).__name__,
                            )
                            self.env.cr.rollback()
                            account._handle_sync_failure(
                                flow="order_sync", amazon_order_ref=amazon_order_ref
                            )
                            continue

                        last_order_update = dateutil.parser.parse(
                            order_data["LastUpdateDate"]
                        )
                        account.last_orders_sync = last_order_update.replace(
                            tzinfo=None
                        )
                        if auto_commit:
                            amazon_utils.commit_preserving_credentials(
                                account, processed=1
                            )
            except amazon_utils.AmazonRateLimitError as error:
                _debug.logic(
                    "orders_sync_interrupted",
                    account=account,
                    reason="rate_limit",
                    operation=error.operation,
                )
                _logger.info(
                    "Rate limit reached while synchronizing sales orders for Amazon account with "
                    "id %s. Operation: %s",
                    account.id,
                    error.operation,
                )
                continue

            _debug.lifecycle(
                "orders_sync_watermark_set",
                account=account,
                last_orders_sync=status_update_upper_limit,
            )
            account.last_orders_sync = status_update_upper_limit.replace(tzinfo=None)

    def _sync_order_by_reference(self, amazon_order_ref) -> dict:
        self.check_singleton()
        amazon_utils.check_account_is_set_up(self)

        order_data = amazon_utils.send_sp_api_request(
            self, "getOrder", path_parameter=amazon_order_ref
        )["payload"]
        if not order_data:
            raise UserError(
                self.env._("The provided reference does not match any Amazon order.")
            )
        if order_data["MarketplaceId"] not in self.active_marketplace_ids.mapped(
            "api_ref"
        ):
            raise UserError(
                self.env._("The order was not found on this account's marketplaces.")
            )

        order = self._process_order_data(order_data)
        if not order:
            amazon_status = order_data["OrderStatus"]
            fulfillment_channel = order_data["FulfillmentChannel"]
            raise ValidationError(
                self.env._(
                    "The Amazon order with reference %(ref)s was not recovered because its status"
                    " (%(status)s) is not eligible for synchronization for its fulfillment channel"
                    " (%(channel)s).",
                    ref=amazon_order_ref,
                    status=amazon_status,
                    channel=fulfillment_channel,
                )
            )
        return {
            "name": order.display_name,
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "view_mode": "form",
            "res_id": order.id,
        }

    def _process_order_data(self, order_data):
        self.check_singleton()

        amazon_order_ref = order_data["AmazonOrderId"]
        if not isinstance(amazon_order_ref, str):
            raise TypeError(
                f"Invalid AmazonOrderId, should be a string: {amazon_order_ref!r}"
            )
        order = self.env["sale.order"].search(
            [("amazon_order_ref", "=", amazon_order_ref)], limit=1
        )
        amazon_status = order_data["OrderStatus"]
        fulfillment_channel = order_data["FulfillmentChannel"]
        if not order:
            if amazon_status in const.STATUS_TO_SYNCHRONIZE[fulfillment_channel]:
                order = self._create_order_from_data(order_data)
                if order.amazon_channel == "fba":
                    self._create_stock_moves(order)
                elif order.amazon_channel == "fbm":
                    order.with_context(mail_notrack=True).action_lock()
                _debug.lifecycle(
                    "amazon_order_created", order=order, channel=order.amazon_channel
                )
                _logger.info(
                    "Created a new sales order with amazon_order_ref %(ref)s for Amazon account"
                    " with id %(id)s.",
                    {"ref": amazon_order_ref, "id": self.id},
                )
            else:
                _debug.logic(
                    "amazon_order_ignored",
                    ref=amazon_order_ref,
                    status=amazon_status,
                    channel=fulfillment_channel,
                )
                _logger.info(
                    "Ignored Amazon order with reference %(ref)s and status %(status)s for Amazon"
                    " account with id %(account_id)s.",
                    {
                        "ref": amazon_order_ref,
                        "status": amazon_status,
                        "account_id": self.id,
                    },
                )
        else:
            unsynced_pickings = order.picking_ids.filtered(
                lambda picking: (
                    picking.amazon_sync_status != "done" and picking.state != "cancel"
                )
            )
            if amazon_status == "Canceled" and order.state != "cancel":
                _debug.lifecycle("amazon_order_cancelled", order=order)
                order._action_cancel()
                _logger.info(
                    "Cancelled sales order with amazon_order_ref %(ref)s for Amazon account with id"
                    " %(id)s.",
                    {"ref": amazon_order_ref, "id": self.id},
                )
            elif (
                amazon_status == "Shipped"
                and fulfillment_channel == "MFN"
                and unsynced_pickings
            ):
                _debug.lifecycle(
                    "picking_sync_forced_done", order=order, pickings=unsynced_pickings
                )
                unsynced_pickings.amazon_sync_status = "done"
                _logger.info(
                    "Forced the picking synchronization status to 'done' for sales order with"
                    " Amazon order reference %(ref)s and Amazon account with id %(id)s.",
                    {"ref": amazon_order_ref, "id": self.id},
                )
            else:
                _debug.logic(
                    "amazon_order_unchanged",
                    order=order,
                    status=amazon_status,
                    pickings=unsynced_pickings,
                )
                _logger.info(
                    "Ignored already synchronized sales order with amazon_order_ref %(ref)s for"
                    " Amazon account with id %(id)s.",
                    {"ref": amazon_order_ref, "id": self.id},
                )
        return order

    def _create_order_from_data(self, order_data):
        self.check_singleton()
        order_vals = self._prepare_order_values(order_data)
        return (
            self.env["sale.order"]
            .with_context(mail_create_nosubscribe=True)
            .with_company(self.company_id)
            .create(order_vals)
        )

    def _prepare_order_values(self, order_data):
        shipping_code = order_data.get("ShipServiceLevel")
        shipping_product = self._get_or_create_matching_product(
            shipping_code, "shipping_product", "Shipping", "service"
        )
        amazon_order_ref = order_data["AmazonOrderId"]
        currency_code = order_data.get("OrderTotal", {}).get("CurrencyCode")
        if currency_code:
            currency = (
                self.env["res.currency"]
                .with_context(active_test=False)
                .search([("name", "=", currency_code)], limit=1)
            )
        elif order_data.get("IsReplacementOrder") == "true":
            replaced_order = self.env["sale.order"].search(
                [("amazon_order_ref", "=", order_data["ReplacedOrderId"])], limit=1
            )
            currency = replaced_order.currency_id
        else:
            raise ValidationError(
                self.env._(
                    "The Amazon order with reference %(ref)s was not recovered because its currency"
                    " was missing from the Amazon order data.",
                    ref=amazon_order_ref,
                )
            )
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

        fulfillment_channel = order_data["FulfillmentChannel"]
        purchase_date = dateutil.parser.parse(order_data["PurchaseDate"]).replace(
            tzinfo=None
        )
        order_vals = {
            "origin": f"Amazon Order {amazon_order_ref}",
            "state": "done",
            "locked": fulfillment_channel == "AFN",
            "date_order": purchase_date,
            "partner_id": contact_partner.id,
            "pricelist_id": self._get_or_create_pricelist(currency).id,
            "line_ids": [
                Command.create(order_line_values)
                for order_line_values in order_lines_values
            ],
            "partner_shipping_id": delivery_partner.id,
            "require_signature": False,
            "require_payment": False,
            "fiscal_position_id": fiscal_position.id,
            "company_id": self.company_id.id,
            "user_id": self.user_id.id,
            "team_id": self.team_id.id,
            "amazon_order_ref": amazon_order_ref,
            "amazon_channel": "fba" if fulfillment_channel == "AFN" else "fbm",
        }
        if fulfillment_channel == "AFN" and self.location_id.warehouse_id:
            order_vals["warehouse_id"] = self.location_id.warehouse_id.id
        return order_vals

    def _get_or_create_partners_from_data(self, order_data) -> tuple:
        self.check_singleton()

        amazon_order_ref = order_data["AmazonOrderId"]
        anonymized_email = order_data["BuyerInfo"].get("BuyerEmail", "")
        buyer_name = order_data["BuyerInfo"].get("BuyerName", "")
        fulfillment_channel = order_data["FulfillmentChannel"]
        shipping_address_info = order_data.get("ShippingAddress", {})
        shipping_address_name = shipping_address_info.get("Name", "")
        street = shipping_address_info.get("AddressLine1", "")
        address_line2 = shipping_address_info.get("AddressLine2", "")
        address_line3 = shipping_address_info.get("AddressLine3", "")
        street2 = (
            "%s %s" % (address_line2, address_line3)
            if address_line2 or address_line3
            else None
        )
        zip_code = shipping_address_info.get("PostalCode", "")
        city = shipping_address_info.get("City", "")
        country_code = shipping_address_info.get("CountryCode", "")
        state_code = shipping_address_info.get("StateOrRegion", "")
        phone = shipping_address_info.get("Phone", "")
        is_company = shipping_address_info.get("AddressType") == "Commercial"
        country = self.env["res.country"].search([("code", "=", country_code)], limit=1)
        state = self.env["res.country.state"].search(
            [
                ("country_id", "=", country.id),
                "|",
                ("code", "=ilike", state_code),
                ("name", "=ilike", state_code),
            ],
            limit=1,
        )
        partner_vals = {
            "street": street,
            "street2": street2,
            "zip": zip_code,
            "city": city,
            "country_id": country.id,
            "state_id": state.id,
            "phone_ids": [Command.create({"number": phone, "type": "landline"})]
            if phone
            else False,
            "customer_rank": 1,
            "company_id": self.company_id.id,
            "email": anonymized_email,
        }

        contact = (
            self.env["res.partner"].search(
                [
                    *self.env["res.partner"]._check_company_domain(self.company_id),
                    ("type", "=", "contact"),
                    ("name", "=", buyer_name),
                    ("email", "=", anonymized_email),
                ],
                limit=1,
            )
            if anonymized_email
            else None
        )
        if not contact:
            contact_name = buyer_name or f"Amazon Customer # {amazon_order_ref}"
            contact = (
                self.env["res.partner"]
                .with_context(tracking_disable=True)
                .create(
                    {
                        "name": contact_name,
                        "is_company": is_company,
                        **partner_vals,
                    }
                )
            )
            if not contact.state_id and state_code and fulfillment_channel == "MFN":
                contact._amazon_create_activity_set_state(self.user_id.id, state_code)

        delivery = (
            contact
            if (
                contact.name == shipping_address_name
                and contact.street == street
                and (not contact.street2 or contact.street2 == street2)
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
                    *self.env["res.partner"]._check_company_domain(self.company_id),
                    ("parent_id", "=", contact.id),
                    ("type", "=", "delivery"),
                    ("name", "=", shipping_address_name),
                    ("street", "=", street),
                    "|",
                    ("street2", "=", False),
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
            if not delivery.state_id and state_code and fulfillment_channel == "MFN":
                delivery._amazon_create_activity_set_state(self.user_id.id, state_code)

        return contact, delivery

    def _prepare_order_lines_values(
        self, order_data, currency, fiscal_pos, shipping_product
    ):

        def pull_items_data(amazon_order_ref_):
            items_data_ = []
            has_next_page_ = True
            while has_next_page_:
                items_batch_data_, has_next_page_ = amazon_utils.pull_batch_data(
                    self, "getOrderItems", {}, path_parameter=amazon_order_ref_
                )
                items_data_ += items_batch_data_["OrderItems"]
            return items_data_

        self.check_singleton()

        amazon_order_ref = order_data["AmazonOrderId"]
        marketplace_api_ref = order_data["MarketplaceId"]
        order_fulfillment_channel = (
            order_data["FulfillmentChannel"] == "MFN" and "fbm"
        ) or "fba"
        order_last_update = dateutil.parser.parse(
            order_data["LastUpdateDate"], ignoretz=True
        )

        items_data = pull_items_data(amazon_order_ref)

        order_lines_values = []
        for item_data in items_data:
            sku = item_data["SellerSKU"]
            marketplace = self.active_marketplace_ids.filtered(
                lambda m: m.api_ref == marketplace_api_ref
            )
            offer = self._acquire_offer(sku, marketplace)
            if (
                offer.amazon_channel != order_fulfillment_channel
                and self.last_orders_sync <= order_last_update
            ):
                if (
                    offer.amazon_channel == "fbm"
                    and offer.sync_stock
                    and order_fulfillment_channel == "fba"
                ):
                    offer.amazon_sync_status = "reset"
                    _logger.info(
                        "Amazon fulfillment channel switch detected (FBM -> FBA). Scheduled an"
                        " inventory reset for offer: %s.",
                        offer.sku,
                    )
                offer.amazon_channel = False
            product_taxes = offer.product_id.taxes_id.filtered_domain(
                [*self.env["account.tax"]._check_company_domain(self.company_id)]
            )
            main_condition = item_data.get("ConditionId")
            sub_condition = item_data.get("ConditionSubtypeId")
            if not main_condition or main_condition.lower() == "new":
                description = "[%s] %s" % (sku, item_data["Title"])
            else:
                item_title = item_data["Title"]
                description = self.env._(
                    "[%(sku)s] %(item_title)s\nCondition: %(main_condition)s - %(sub_condition)s",
                    sku=sku,
                    item_title=item_title,
                    main_condition=main_condition,
                    sub_condition=sub_condition,
                )
            sales_price = float(item_data.get("ItemPrice", {}).get("Amount", 0.0))
            tax_amount = float(item_data.get("ItemTax", {}).get("Amount", 0.0))
            original_subtotal = (
                sales_price - tax_amount if marketplace.tax_included else sales_price
            )
            taxes = fiscal_pos.map_tax(product_taxes) if fiscal_pos else product_taxes
            subtotal = self._get_price_from_order_amounts(
                original_subtotal, tax_amount, taxes, currency, fiscal_pos
            )
            promo_discount = float(
                item_data.get("PromotionDiscount", {}).get("Amount", "0")
            )
            promo_disc_tax = float(
                item_data.get("PromotionDiscountTax", {}).get("Amount", "0")
            )
            original_promo_discount_subtotal = (
                promo_discount - promo_disc_tax
                if marketplace.tax_included
                else promo_discount
            )
            promo_discount_subtotal = self._get_price_from_order_amounts(
                original_promo_discount_subtotal,
                promo_disc_tax,
                taxes,
                currency,
                fiscal_pos,
            )
            amazon_item_ref = item_data["OrderItemId"]
            order_lines_values.append(
                self._convert_to_order_line_values(
                    item_data=item_data,
                    product_id=offer.product_id.id,
                    description=description,
                    subtotal=subtotal,
                    tax_ids=taxes.ids,
                    quantity=item_data["QuantityOrdered"],
                    discount=promo_discount_subtotal,
                    amazon_item_ref=amazon_item_ref,
                    amazon_offer_id=offer.id,
                )
            )

            if item_data.get("IsGift", "false") == "true":
                item_gift_info = item_data.get("BuyerInfo", {})
                gift_wrap_code = item_gift_info.get("GiftWrapLevel")
                gift_wrap_price = float(
                    item_gift_info.get("GiftWrapPrice", {}).get("Amount", "0")
                )
                if gift_wrap_code and gift_wrap_price != 0:
                    gift_wrap_product = self._get_or_create_matching_product(
                        gift_wrap_code, "default_product", "Amazon Sales", "consu"
                    )
                    gift_wrap_product_taxes = (
                        gift_wrap_product.taxes_id.filtered_domain(
                            [
                                *self.env["account.tax"]._check_company_domain(
                                    self.company_id
                                )
                            ]
                        )
                    )
                    gift_wrap_taxes = (
                        fiscal_pos.map_tax(gift_wrap_product_taxes)
                        if fiscal_pos
                        else gift_wrap_product_taxes
                    )
                    gift_wrap_tax_amount = float(
                        item_gift_info.get("GiftWrapTax", {}).get("Amount", "0")
                    )
                    original_gift_wrap_subtotal = (
                        gift_wrap_price - gift_wrap_tax_amount
                        if marketplace.tax_included
                        else gift_wrap_price
                    )
                    gift_wrap_subtotal = self._get_price_from_order_amounts(
                        original_gift_wrap_subtotal,
                        gift_wrap_tax_amount,
                        gift_wrap_taxes,
                        currency,
                        fiscal_pos,
                    )
                    order_lines_values.append(
                        self._convert_to_order_line_values(
                            item_data=item_data,
                            product_id=gift_wrap_product.id,
                            description=self.env._(
                                "[%(gift_wrap_code)s] Gift Wrapping Charges for %(product)s",
                                gift_wrap_code=gift_wrap_code,
                                product=offer.product_id.name,
                            ),
                            subtotal=gift_wrap_subtotal,
                            tax_ids=gift_wrap_taxes.ids,
                        )
                    )
                gift_message = item_gift_info.get("GiftMessageText")
                if gift_message:
                    order_lines_values.append(
                        self._convert_to_order_line_values(
                            item_data=item_data,
                            description=self.env._("Gift message:\n%s", gift_message),
                            display_type="line_note",
                        )
                    )

            shipping_code = order_data.get("ShipServiceLevel")
            shipping_price = float(
                item_data.get("ShippingPrice", {}).get("Amount", "0")
            )
            if shipping_code and shipping_price != 0:
                shipping_product_taxes = shipping_product.taxes_id.filtered_domain(
                    [*self.env["account.tax"]._check_company_domain(self.company_id)]
                )
                shipping_taxes = (
                    fiscal_pos.map_tax(shipping_product_taxes)
                    if fiscal_pos
                    else shipping_product_taxes
                )
                shipping_tax_amount = float(
                    item_data.get("ShippingTax", {}).get("Amount", "0")
                )
                origin_ship_subtotal = (
                    shipping_price - shipping_tax_amount
                    if marketplace.tax_included
                    else shipping_price
                )
                shipping_subtotal = self._get_price_from_order_amounts(
                    origin_ship_subtotal,
                    shipping_tax_amount,
                    shipping_taxes,
                    currency,
                    fiscal_pos,
                )
                ship_discount = float(
                    item_data.get("ShippingDiscount", {}).get("Amount", "0")
                )
                ship_disc_tax = float(
                    item_data.get("ShippingDiscountTax", {}).get("Amount", "0")
                )
                origin_ship_disc_subtotal = (
                    ship_discount - ship_disc_tax
                    if marketplace.tax_included
                    else ship_discount
                )
                ship_discount_subtotal = self._get_price_from_order_amounts(
                    origin_ship_disc_subtotal,
                    ship_disc_tax,
                    shipping_taxes,
                    currency,
                    fiscal_pos,
                )
                order_lines_values.append(
                    self._convert_to_order_line_values(
                        item_data=item_data,
                        product_id=shipping_product.id,
                        description=self.env._(
                            "[%(shipping_code)s] Delivery Charges for %(product)s",
                            shipping_code=shipping_code,
                            product=offer.product_id.name,
                        ),
                        subtotal=shipping_subtotal,
                        tax_ids=shipping_taxes.ids,
                        discount=ship_discount_subtotal,
                    )
                )

        return order_lines_values

    def _convert_to_order_line_values(self, **kwargs) -> dict:
        subtotal = kwargs.get("subtotal", 0)
        quantity = kwargs.get("quantity", 1)
        return {
            "name": kwargs.get("description", ""),
            "product_id": kwargs.get("product_id"),
            "price_unit": subtotal / quantity if quantity else 0,
            "tax_ids": [Command.set(kwargs.get("tax_ids", []))],
            "product_qty": quantity,
            "discount": (kwargs.get("discount", 0) / subtotal) * 100 if subtotal else 0,
            "display_type": kwargs.get("display_type", False),
            "amazon_item_ref": kwargs.get("amazon_item_ref"),
            "amazon_offer_id": kwargs.get("amazon_offer_id"),
        }

    def _acquire_offer(self, sku: str, marketplace: AmazonMarketplace) -> AmazonOffer:
        self.check_singleton()

        offer = self.offer_ids.filtered(lambda o: o.sku == sku)
        _debug.logic(
            "offer_lookup", account=self, sku=sku, offer=offer, found=bool(offer)
        )
        if not offer:
            offer = (
                self.env["amazon.offer"]
                .with_context(tracking_disable=True)
                .create(
                    {
                        "account_id": self.id,
                        "marketplace_id": marketplace.id,
                        "product_id": self._get_or_create_matching_product(
                            sku, "default_product", "Amazon Sales", "consu"
                        ).id,
                        "sku": sku,
                        "amazon_feed_ref": "{}",
                    }
                )
            )
        elif "sale_amazon.default_product" in offer.product_id._get_external_ids().get(
            offer.product_id.id, []
        ):
            product = self._get_or_create_matching_product(
                sku, "", "", "", fallback=False
            )
            _debug.logic(
                "offer_product_rematched",
                account=self,
                offer=offer,
                sku=sku,
                product=product,
                rematched=bool(product),
            )
            if product:
                offer.product_id = product.id
        return offer

    def _get_or_create_pricelist(self, currency):
        self.check_singleton()
        pricelist = (
            self.env["product.pricelist"]
            .with_context(active_test=False)
            .search(
                [
                    *self.env["product.pricelist"]._check_company_domain(
                        self.company_id
                    ),
                    ("currency_id", "=", currency.id),
                ],
                limit=1,
            )
        )
        _debug.logic(
            "pricelist_lookup",
            account=self,
            currency=currency,
            pricelist=pricelist,
            found=bool(pricelist),
        )
        if not pricelist:
            pricelist = (
                self.env["product.pricelist"]
                .with_context(tracking_disable=True)
                .create(
                    {
                        "name": "Amazon Pricelist %s" % currency.name,
                        "company_id": self.company_id.id,
                        "active": False,
                        "currency_id": currency.id,
                    }
                )
            )
        return pricelist

    def _get_or_create_matching_product(
        self,
        internal_reference: str | None,
        default_xmlid: str | None,
        default_name: str | None,
        default_type: str | None,
        fallback: bool = True,
    ) -> ProductProduct:
        self.check_singleton()
        product = self.env["product.product"].search(
            [
                *self.env["product.product"]._check_company_domain(self.company_id),
                ("default_code", "=", internal_reference),
            ],
            limit=1,
        )
        if not product and fallback:
            product = self.env.ref(
                "sale_amazon.%s" % default_xmlid, raise_if_not_found=False
            )
            _debug.logic(
                "product_matched",
                account=self,
                reference=internal_reference,
                product=product,
                by="default_xmlid",
                xmlid=default_xmlid,
            )
        if not product and fallback:
            product = self.env["product.product"]._restore_data_product(
                default_name, default_type, default_xmlid
            )
            _debug.lifecycle(
                "default_product_restored",
                account=self,
                product=product,
                xmlid=default_xmlid,
            )
        return product

    def _get_price_from_order_amounts(
        self, subtotal, tax_amount, taxes, currency, _fiscal_pos=None
    ):
        total = subtotal + tax_amount
        return price_from_tax_included_total(self.env, total, taxes, currency)

    def _create_stock_moves(self, order):
        customers_location = self.env.ref("stock.stock_location_customers")
        _debug.pipeline(
            "stock_moves_generation_started",
            account=self,
            order=order,
            lines=len(order.line_ids),
        )
        for order_line in order.line_ids.filtered(
            lambda l: l.product_id.type != "service" and not l.display_type
        ):
            stock_move = self.env["stock.move"].create(
                {
                    "company_id": self.company_id.id,
                    "product_id": order_line.product_id.id,
                    "product_uom_qty": order_line.product_qty,
                    "product_uom_id": order_line.product_uom_id.id,
                    "location_id": self.location_id.id,
                    "location_dest_id": customers_location.id,
                    "state": "confirmed",
                    "sale_line_id": order_line.id,
                }
            )
            stock_move._update_quantity_done(order_line.product_qty)
            stock_move.picked = (
                True
            )
            stock_move._action_done()

    def _sync_inventory(self) -> None:
        self = self or self.search([])
        accounts = self.filtered("synchronize_inventory")
        if not accounts:
            _debug.logic("inventory_sync_skipped", reason="no_account_synchronizes")
            return

        def to_sync(offer_):
            return offer_.sync_stock or offer_.amazon_sync_status == "reset"

        accounts.offer_ids.filtered(to_sync).product_id._compute_quantities()

        for account in accounts:
            amazon_utils.check_account_is_set_up(account)
            offers = account.offer_ids.filtered(to_sync)
            with _debug.perf("inventory_sync", account=account) as span:
                span.set(offers=len(offers), candidates=len(account.offer_ids))
                offers._update_inventory_availability(account)

        next_call = fields.Datetime.now() + timedelta(minutes=10)
        self.env["ir.cron"]._trigger_ref(
            "sale_amazon.ir_cron_sync_amazon_feeds", at=next_call
        )

    def _sync_feeds(self) -> None:
        self = self or self.search([])

        accounts_with_offers = self.filtered(
            lambda a: any(o.amazon_sync_status == "processing" for o in a.offer_ids)
        )
        pickings_by_account = self.env["stock.picking"]._get_pickings_by_account(
            "processing", tuple(self.ids)
        )

        _debug.pipeline(
            "feeds_sync_started",
            accounts_with_offers=accounts_with_offers,
            accounts_with_pickings=len(pickings_by_account),
        )

        for account in accounts_with_offers:
            amazon_utils.check_account_is_set_up(account)
            offers = account.offer_ids.filtered(
                lambda o: o.amazon_sync_status == "processing"
            )
            account._pull_feeds_status(offers, "inventory_sync")
        for account, pickings in pickings_by_account.items():
            amazon_utils.check_account_is_set_up(account)
            account._pull_feeds_status(pickings, "picking_sync")

        any_processing_feed = any(
            offer.amazon_sync_status == "processing"
            for offer in accounts_with_offers.offer_ids
        ) or any(
            account_pickings.filtered(lambda p: p.amazon_sync_status == "processing")
            for account_pickings in pickings_by_account.values()
        )
        _debug.logic("feeds_sync_rescheduled", scheduled=any_processing_feed)
        if any_processing_feed:
            next_call = fields.Datetime.now() + timedelta(minutes=10)
            self.env["ir.cron"]._trigger_ref(
                "sale_amazon.ir_cron_sync_amazon_feeds", at=next_call
            )

    def _pull_feeds_status(self, records, flow) -> None:
        self.check_singleton()

        if flow == "inventory_sync":
            feed_data_by_offer = records._get_feed_data()
            records_by_feed_ref = records.grouped(
                lambda o: feed_data_by_offer.get(o, {}).get("amazon_feed_ref")
            )
        elif flow == "picking_sync":
            records_by_feed_ref = records.grouped("amazon_feed_ref")
        else:
            _debug.logic(
                "feed_status_pull_refused",
                account=self,
                flow=flow,
                reason="unknown_flow",
            )
            return
        _debug.pipeline(
            "feed_status_pull_started",
            account=self,
            flow=flow,
            records=len(records),
            feeds=len(records_by_feed_ref),
        )

        def parse_json_report_document(report_):
            errors_ = {}
            for result in report_["issues"]:
                if result["severity"] == "ERROR":
                    errors_.setdefault(result.get("messageId"), []).append(
                        get_error_message(result["code"], result["message"])
                    )
            return errors_

        def parse_xml_report_document(report_):
            errors_ = {}
            for result_ in report_.find("Message/ProcessingReport").iter("Result"):
                if result_.find("ResultCode").text != "Error":
                    continue
                if (order_ := result_.find("AdditionalInfo/AmazonOrderID")) is not None:
                    order_ref_ = order_.text
                else:
                    order_ref_ = None
                errors_.setdefault(order_ref_, []).append(
                    get_error_message(
                        result_.find("ResultMessageCode").text,
                        result_.find("ResultDescription").text,
                    )
                )
            return errors_

        def get_error_message(code, message):
            return self.env._(
                "Error (%(code)s): %(message)s", code=code, message=message
            )

        errors_by_record = {}
        for feed_ref, feed_records in records_by_feed_ref.items():
            if not feed_ref:
                _debug.logic(
                    "feed_status_skipped",
                    account=self,
                    flow=flow,
                    records=feed_records,
                    reason="no_feed_ref",
                )
                _logger.warning(
                    "Failed to load the feed reference for the records with IDs"
                    " %(feed_record_ids)r. Skipping the synchronization attempt only for these IDs."
                    " The next synchronization will be attempted later.",
                    {"feed_record_ids": feed_records.ids},
                )
                continue
            feed_data = amazon_utils.send_sp_api_request(
                self, "getFeed", path_parameter=feed_ref
            )
            feed_status = feed_data["processingStatus"]
            report_document_ref = feed_data.get("resultFeedDocumentId")
            _debug.pipeline(
                "feed_status_pulled",
                account=self,
                flow=flow,
                feed_ref=feed_ref,
                status=feed_status,
                records=len(feed_records),
                has_report=bool(report_document_ref),
            )

            if feed_status == "DONE":
                try:
                    report = amazon_utils.get_feed_document(self, report_document_ref)
                except amazon_utils.AmazonRateLimitError:
                    raise
                except ValidationError:
                    _debug.logic(
                        "feed_report_skipped",
                        account=self,
                        feed_ref=feed_ref,
                        reason="business_error",
                    )
                    _logger.exception(
                        "A business error occurred while processing feed %(feed_ref)s for Amazon"
                        " account with id %(account_id)s. Skipping the feed and moving to the next"
                        " one.",
                        {"feed_ref": feed_ref, "account_id": self.id},
                    )
                else:
                    if flow == "inventory_sync":
                        report_errors = parse_json_report_document(report)

                        def message_key(o):
                            return feed_data_by_offer[o].get("messageId")
                    else:
                        report_errors = parse_xml_report_document(report)

                        def message_key(p):
                            return p.sale_id.amazon_order_ref

                    if not report_errors:
                        _debug.lifecycle(
                            "feed_records_done",
                            account=self,
                            flow=flow,
                            feed_ref=feed_ref,
                            records=feed_records,
                        )
                        feed_records.amazon_sync_status = "done"
                        _logger.info(
                            "Synchronized feed %(feed_ref)s for Amazon account with id"
                            " %(account_id)s.",
                            {"feed_ref": feed_ref, "account_id": self.id},
                        )
                        continue

                    error_records = feed_records.browse(
                        [
                            record.id
                            for record in feed_records
                            if message_key(record) in report_errors
                        ]
                    )
                    _debug.lifecycle(
                        "feed_records_errored",
                        account=self,
                        flow=flow,
                        feed_ref=feed_ref,
                        records=error_records,
                        messages=len(report_errors),
                        unattributed="yes" if None in report_errors else "no",
                    )
                    error_records.amazon_sync_status = "error"
                    for record in error_records:
                        errors_by_record.setdefault(record, set()).update(
                            report_errors[message_key(record)]
                        )
                    unprocessed_records = feed_records.filtered(
                        lambda p: p.amazon_sync_status == "processing"
                    )

                    if None in report_errors:
                        unprocessed_records.amazon_sync_status = "error"
                        for record in unprocessed_records:
                            errors_by_record.setdefault(record, set()).update(
                                report_errors[None]
                            )
                    else:
                        unprocessed_records.amazon_sync_status = "done"
                    _logger.info(
                        "Found errors while synchronizing feed %(feed_ref)s for Amazon account with"
                        " id %(account_id)s.",
                        {"feed_ref": feed_ref, "account_id": self.id},
                    )

            elif feed_status in [
                "IN_QUEUE",
                "IN_PROGRESS",
            ]:
                _logger.info(
                    "Ignoring in progress feed %(feed_ref)s for Amazon account with id"
                    " %(account_id)s.",
                    {"feed_ref": feed_ref, "account_id": self.id},
                )

            elif (
                feed_status == "CANCELLED"
            ):
                feed_records.amazon_sync_status = "pending"
                if flow == "inventory_sync":
                    _logger.info(
                        "Re-scheduling a synchronization of inventory for offers of cancelled"
                        " feed %(feed_ref)s for Amazon account with id %(account_id)s.",
                        {"feed_ref": feed_ref, "account_id": self.id},
                    )
                elif flow == "picking_sync":
                    _logger.info(
                        "Re-scheduling a synchronization for pickings of cancelled feed %(feed_ref)s"
                        " for Amazon account with id %(account_id)s.",
                        {"feed_ref": feed_ref, "account_id": self.id},
                    )

            elif feed_status == "FATAL":
                for record in feed_records:
                    errors_by_record.setdefault(record, set()).add(None)
                feed_records.amazon_sync_status = "error"

        if errors_by_record:
            error_messages = []
            for r, errors in errors_by_record.items():
                for error in errors:
                    if error and flow == "picking_sync":
                        r.message_post(
                            body=Markup("%s<br/>%s")
                            % (
                                self.env._(
                                    "The synchronization with Amazon failed. Amazon gave us this "
                                    "information about the problem:"
                                ),
                                error,
                            )
                        )
                    if flow == "inventory_sync":
                        error_messages.append({"sku": r.sku, "message": error})
                    elif flow == "picking_sync":
                        error_messages.append(
                            {"order_ref": r.sale_id.amazon_order_ref, "message": error}
                        )

            self._handle_sync_failure(flow=flow, error_messages=error_messages)

    def _handle_sync_failure(
        self, flow, amazon_order_ref=False, error_messages=False
    ) -> None:
        if flow == "order_sync":
            _logger.error(
                "Failed to synchronize order with amazon reference %(ref)s for amazon.account with "
                "id %(account_id)s (seller id %(seller_id)s).",
                {
                    "ref": amazon_order_ref,
                    "account_id": self.id,
                    "seller_id": self.seller_key,
                },
            )
            mail_template_id = "sale_amazon.order_sync_failure"
        elif flow == "inventory_sync":
            _logger.error(
                "Failed to synchronize the inventory for offers in amazon.account with id "
                "%(account_id)s (seller id %(seller_id)s).",
                {"account_id": self.id, "seller_id": self.seller_key},
            )
            mail_template_id = "sale_amazon.inventory_sync_failure"
        else:
            _logger.error(
                "Failed to synchronize pickings for amazon.account with id %(account_id)s "
                "(seller id %(seller_id)s).",
                {"account_id": self.id, "seller_id": self.seller_key},
            )
            mail_template_id = "sale_amazon.picking_sync_failure"

        mail_template = self.env.ref(mail_template_id, raise_if_not_found=False)
        if not mail_template:
            _logger.warning(
                "The mail template with xmlid %s has been deleted.", mail_template_id
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
                amazon_order_ref=amazon_order_ref,
                error_messages=error_messages,
                amazon_account=self.name,
            ).send_mail(self.env.user.id)
            _logger.info(
                "Sent synchronization failure notification email to %s",
                ", ".join(responsible_emails),
            )
