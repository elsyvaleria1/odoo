import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from freezegun import freeze_time

from odoo import Command, _
from odoo.exceptions import UserError
from odoo.tests.common import HttpCase, tagged
from odoo.tools import mute_logger, security

from odoo.addons.sale_shopee import const
from odoo.addons.sale_shopee import utils as shopee_utils
from odoo.addons.sale_shopee.controllers import onboarding
from odoo.addons.sale_shopee.tests import common


@tagged("post_install", "-at_install")
class TestShopee(common.TestShopeeCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.startClassPatcher(freeze_time("2020-02-01"))

    def test_shop_status_banned(self):
        """Test the shop status when the shop is banned.

        No synchronization should be performed when the shop is banned.
        """

        def get_shopee_api_response_mock(_shop, operation_, *_args):
            if operation_ == "get_shop_info":
                return dict(
                    common.OPERATIONS_RESPONSES_MAP[operation_], status="BANNED"
                )
            else:
                return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=get_shopee_api_response_mock,
        ):
            shop = self.shop
            self.assertEqual(shop.status, "active")

            shop._update_shop_information(force_update=True)
            shop._sync_orders(auto_commit=False)
            shop._sync_inventory(auto_commit=False)

            self.assertEqual(shop.status, "error")
            self.assertEqual(shop.last_orders_sync_date, self.initial_sync_date)
            self.assertEqual(self.item.last_inventory_sync_date, self.initial_sync_date)

    # --- Sync Orders --- #
    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_orders_full(self):
        """Test the orders synchronization with on-the-fly creation of all required records.

        1 order with 3 order lines is created: a product line and an adjustment line.
        """
        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=lambda _shop, operation, *_args: common.OPERATIONS_RESPONSES_MAP[
                operation
            ],
        ):
            self.shop._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("shopee_order_ref", "=", common.ORDER_SN_MOCK)]
            )
            order_lines = self.env["sale.order.line"].search(
                [("order_id", "=", order.id)]
            )
            product_line = order_lines.filtered(
                lambda l: l.product_id.default_code == "TEST_SKU"
            )

            self.assertEqual(
                self.shop.last_orders_sync_date,
                datetime.now(),
                msg="The last_orders_sync_date should be equal to current datetime after a"
                " successful run",
            )
            self.assertEqual(len(order), 1)
            self.assertEqual(len(order_lines), 1)  # product line only
            self.assertRecordValues(
                order,
                [
                    {
                        "origin": _(
                            "Shopee Order %(order)s at mock_shopee_shop",
                            order=common.ORDER_SN_MOCK,
                        ),
                        "date_order": datetime(2020, 1, 15, 1),
                        "company_id": self.shop.company_id.id,
                        "user_id": self.shop.user_id.id,
                        "team_id": self.shop.team_id.id,
                        "warehouse_id": self.shop.fbs_location_id.warehouse_id.id,
                        "shopee_fulfillment_type": "fbm",
                        "amount_total": 160.0,
                    }
                ],
            )
            self.assertRecordValues(
                product_line,
                [
                    {
                        "price_unit": 100,
                        "product_qty": 4.0,
                        "product_id": self.item.product_id.id,
                    }
                ],
            )

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_orders_partial(self):
        """Test the orders synchronization interruption with API throttling.

        Note: last_orders_sync_date is committed to DB after each successful period of
        synchronization.
              e.g. each synchronizing period is 10 days (check ShopeeShop._get_order_list)
                   After synchronizing 10 days of orders, last_orders_sync_date is updated in DB.
        """

        def get_shopee_api_response_mock(_shop, operation_, *_args):
            """Return a mocked response without making an actual call to the Shopee API.

            Raise a ShopeeRateLimitError when the second order is synchronized, to simulate a
            throttling issue.
            """
            response_ = common.OPERATIONS_RESPONSES_MAP[operation_]
            if operation_ == "get_order_list":
                response_["order_list"].append({"order_sn": "2404098R48UXYZ"})
            elif operation_ == "get_order_detail":
                self.order_count += 1
                if self.order_count == 2:
                    raise shopee_utils.ShopeeRateLimitError(operation_)
            return response_

        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=get_shopee_api_response_mock,
        ):
            self.order_count = 0
            self.shop._sync_orders(auto_commit=False)
            self.assertEqual(
                self.shop.last_orders_sync_date,
                self.initial_sync_date + timedelta(days=const.ORDER_LIST_DAYS_LIMIT),
                msg="The last_orders_sync_date should be equal to the LastUpdateDate of the last"
                " fully synchronized period, which is 10 days.",
            )

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_orders_fail(self):
        """Test the orders synchronization cancellation with API throttling.

        The last order synchronization date should not be updated if the rate limit of one operation
        was reached.
        """

        def get_shopee_api_response_mock(_shop, operation_, *_args):
            """Return a mocked response or raise a ShopeeRateLimitError without making an actual
            call to the Shopee API."""
            if operation_ == "get_order_list":
                raise shopee_utils.ShopeeRateLimitError(operation_)
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=get_shopee_api_response_mock,
        ):
            last_orders_sync_date_copy = self.shop.last_orders_sync_date
            self.shop._sync_orders(auto_commit=False)
            self.assertEqual(
                self.shop.last_orders_sync_date, last_orders_sync_date_copy
            )

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_orders_no_active_shop(self):
        """Test the orders synchronization cancellation with no active shop.

        No order synchronization should be performed as there is no active shop selected for the
        account.
        """

        def get_shopee_api_response_mock(_shop, operation_, *_args):
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=get_shopee_api_response_mock,
        ):
            last_orders_sync_date_copy = self.shop.last_orders_sync_date
            self.account.shop_ids.write({"status": "inactive"})

            self.account.shop_ids._sync_orders(auto_commit=False)

            self.assertEqual(
                self.shop.last_orders_sync_date, last_orders_sync_date_copy
            )

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_orders_fbs(self):
        """Test the orders synchronization with fulfillment type 'Fulfillment By Shopee'

        FBS order should generate a stock move for each product that is not a service and no picking
        """

        def get_shopee_api_response_mock(_shop, operation_, *_args):
            """Return a mocked response without making an actual call to the Shopee API."""
            if operation_ == "get_order_detail":
                return {
                    "order_list": [
                        {
                            **common.ORDER_MOCK,
                            "fulfillment_flag": "fulfilled_by_shopee",
                            "order_status": "SHIPPED",
                        }
                    ]
                }
            else:
                return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=get_shopee_api_response_mock,
        ):
            self.shop._sync_orders(auto_commit=False)  # no order created
            order = self.env["sale.order"].search(
                [("shopee_order_ref", "=", "O123456789")]
            )
            products = order.line_ids.mapped("product_id").filtered(
                lambda p: p.type != "service"
            )
            moves = self.env["stock.move"].search([("product_id", "in", products.ids)])
            picking = self.env["stock.picking"].search([("sale_id", "=", order.id)])

            self.assertEqual(order.shopee_fulfillment_type, "fbs")
            self.assertEqual(len(moves), len(products))
            self.assertEqual(len(picking), 0)

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_orders_cancel(self):
        """Test the orders synchronization to cancel a created order from Shopee.

        Status of the order should be updated to 'cancel' when the order is cancelled on Shopee.
        """

        def get_shopee_api_response_mock(_shop, operation_, *_args):
            """Return a mocked response without making an actual call to the Shopee API."""
            order_status_ = "CANCELLED" if self.order_created else "READY_TO_SHIP"
            if operation_ == "get_order_detail":
                return {
                    "order_list": [{**common.ORDER_MOCK, "order_status": order_status_}]
                }
            else:
                return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=get_shopee_api_response_mock,
        ):
            # Sync an order created on Shopee.
            order_count = self.env["sale.order"].search_count([])
            self.order_created = False
            self.shop._sync_orders(auto_commit=False)
            self.assertEqual(self.env["sale.order"].search_count([]), order_count + 1)

            # Rewind last_orders_sync_date to simulate the order was created before the current time
            self.shop.last_orders_sync_date = datetime.fromtimestamp(
                1579050000
            )  # 2020-01-15

            # Sync an order cancelled from Shopee.
            self.order_created = True
            self.shop._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("shopee_order_ref", "=", "O123456789")]
            )
            self.assertEqual(order.state, "cancel")

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_orders_cancel_abort(self):
        """Test when pickings fetched the shipping label from shopee and then the related order is
        cancelled on Shopee.

        The picking should be cancelled when the order is cancelled on Shopee.
        """

        def get_shopee_api_response_mock(_shop, operation_, *_args):
            """Return a mock response without making an actual call to the Selling Partner API."""
            response_ = common.OPERATIONS_RESPONSES_MAP[operation_]
            order_status_ = "CANCELLED" if self.order_cancelled else "PROCESSED"
            if operation_ == "get_order_detail":
                response_ = {
                    "order_list": [{**common.ORDER_MOCK, "order_status": order_status_}]
                }
            return response_

        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=get_shopee_api_response_mock,
        ):
            # Sync an order created on Shopee.
            self.order_cancelled = False
            self.shop._sync_orders(auto_commit=False)

            # Rewind last_orders_sync_date to simulate the order was created before the current time
            self.shop.last_orders_sync_date = datetime.fromtimestamp(
                1579050000
            )  # 2020-01-15

            # Check the order state and validate the picking.
            order = self.env["sale.order"].search(
                [("shopee_order_ref", "=", common.ORDER_SN_MOCK)]
            )
            self.assertNotEqual(order.state, "shipped")
            picking = self.env["stock.picking"].search([("sale_id", "=", order.id)])
            self.order_cancelled = True

            self.shop._sync_orders(auto_commit=False)  # DEBUG sale != cancel

            self.assertEqual(order.state, "cancel")
            self.assertEqual(picking.state, "cancel")

    # --- Sync Inventory --- #

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_inventory(self):
        """Test the inventory synchronization sends the correct inventory information to Shopee

        The inventory of the product on Shopee is updated as the free quantity of the product and
        the last_inventory_sync_date is updated.
        """

        def get_shopee_api_response_mock(
            _shop, operation_, _params="", body="", _files="", method="GET"
        ):
            """Return a mocked response without making an actual call to the Shopee API."""
            if operation_ == "update_stock":
                self.body = body
                return common.OPERATIONS_RESPONSES_MAP[operation_]
            raise AssertionError(f"unexpected Shopee API call: {operation_}")

        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=get_shopee_api_response_mock,
        ):
            self.shop.synchronize_inventory = True

            self.assertEqual(self.shop.shopee_item_ids, self.item)
            self.assertEqual(self.item.product_id.qty_free, 0)
            self.assertEqual(self.item.last_inventory_sync_date, self.initial_sync_date)

            # setup inventory level of the product to 10
            warehouse_id = self.env["stock.warehouse"].search(
                [("company_id", "=", self.shop.company_id.id)], limit=1
            )
            self.env["stock.quant"].with_context(inventory_mode=True).create(
                {
                    "product_id": self.item.product_id.id,
                    "location_id": warehouse_id.lot_stock_id.id,
                    "inventory_quantity": 10,
                }
            )._apply_inventory()
            self.shop._sync_inventory(auto_commit=False)

            self.assertEqual(
                self.body["item_id"], int(self.item.shopee_item_identifier)
            )
            self.assertEqual(self.body["stock_list"][0]["seller_stock"][0]["stock"], 10)
            self.assertEqual(self.item.last_inventory_sync_date, datetime.now())

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_inventory_is_skipped_when_disabled(self):
        """Test skipping the inventory synchronization when the shop disabled the feature.

        No inventory synchronization should be performed when the shop is disabled.
        """

        def get_shopee_api_response_mock(_shop, operation_, *_args):
            """Return a mocked response without making an actual call to the Shopee API."""
            if operation_ == "update_stock":
                raise AssertionError("the inventory must not be sent to Shopee")
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=get_shopee_api_response_mock,
        ):
            self.shop.synchronize_inventory = False
            self.assertEqual(self.shop.shopee_item_ids, self.item)

            # No error means get_shopee_api_response_mock is not called
            self.shop._sync_inventory(auto_commit=False)

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_inventory_error(self):
        """Test the inventory synchronization error handling.

        An exception should be raised when the inventory synchronization fails.
        """

        class SyncFailureReportedError(Exception):
            pass

        def get_shopee_api_response_mock(_shop, operation_, *_args, **_kwargs):
            """Return a mocked response without making an actual call to the Shopee API."""
            if operation_ == "update_stock":
                raise UserError("update_stock rejected")
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        def _handle_sync_failure(_shop, **_kwargs):
            raise SyncFailureReportedError

        with (
            patch(
                "odoo.addons.sale_shopee.utils.send_shopee_api_request",
                new=get_shopee_api_response_mock,
            ),
            patch(
                "odoo.addons.sale_shopee.models.shopee_shop.ShopeeShop._handle_sync_failure",
                new=_handle_sync_failure,
            ),
        ):
            self.shop.synchronize_inventory = True

            self.assertEqual(self.shop.shopee_item_ids, self.item)
            with self.assertRaises(SyncFailureReportedError):
                self.shop._sync_inventory(auto_commit=False)

    # --- Sync Pickings --- #

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_pickings(self):
        """Test the pickings synchronization.

        A tracking number and shipping label should be created for the FBM order.
        """
        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=lambda _shop, operation_, *_args, **_kwargs: (
                common.OPERATIONS_RESPONSES_MAP[operation_]
            ),
        ):
            # Synchronize the order and generate picking
            self.shop._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("shopee_order_ref", "=", "O123456789")]
            )
            picking = self.env["stock.picking"].search([("sale_id", "=", order.id)])

            self.assertEqual(len(picking), 1)
            self.assertEqual(picking.carrier_id.name, "Fake Ship")
            self.assertEqual(picking.shopee_label_status, "not available")
            self.assertEqual(len(picking.message_ids.attachment_ids), 0)

            # Synchronize the picking
            picking._action_done()
            self.env["stock.picking"]._sync_shopee_pickings(
                tuple(self.shop.ids), auto_commit=False
            )

            self.assertEqual(picking.shopee_label_status, "stored")
            self.assertEqual(picking.carrier_tracking_ref, "MY200448706479IT")
            self.assertEqual(len(picking.message_ids.attachment_ids), 1)

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_pickings_processing(self):
        """Test the pickings synchronization with a temporary processing status.

        The tracking number and shipping label should be created for the FBM order.
        """

        def get_shopee_api_response_mock(_shop, operation_, *_args, **_kwargs):
            """Return a mocked response without making an actual call to the Shopee API."""
            if operation_ == "get_shipping_document_result" and not label_processed:
                return {
                    "result_list": [
                        {
                            "order_sn": common.ORDER_SN_MOCK,
                            "status": "PROCESSING",
                        }
                    ]
                }
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=get_shopee_api_response_mock,
        ):
            label_processed = False
            self.shop._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("shopee_order_ref", "=", "O123456789")]
            )
            picking = self.env["stock.picking"].search([("sale_id", "=", order.id)])

            self.assertEqual(picking.shopee_label_status, "not available")
            self.assertEqual(len(picking.message_ids.attachment_ids), 0)

            picking._action_done()
            self.env["stock.picking"]._sync_shopee_pickings(
                tuple(self.shop.ids), auto_commit=False
            )

            self.assertEqual(picking.shopee_label_status, "processing")
            self.assertEqual(picking.carrier_tracking_ref, "MY200448706479IT")
            self.assertEqual(len(picking.message_ids.attachment_ids), 0)

            label_processed = True
            self.env["stock.picking"]._sync_shopee_pickings(
                tuple(self.shop.ids), auto_commit=False
            )

            self.assertEqual(picking.shopee_label_status, "stored")
            self.assertEqual(len(picking.message_ids.attachment_ids), 1)

    # --- Find Matching Product --- #

    def test_get_or_create_matching_product_search(self):
        """Test the product search based on the internal reference.

        A product should be found with the internal reference.
        """
        product = self.shop._get_or_create_matching_product(
            common.ORDER_ITEM_MOCK["model_sku"], None, None, None
        )
        self.assertEqual(product.name, self.item.product_id.name)
        self.assertEqual(product.default_code, common.ORDER_ITEM_MOCK["model_sku"])

    def test_get_or_create_matching_product_use_fallback(self):
        """Test the product search failure with use of the fallback.

        A fallback product should be returned when the product is not found.
        """
        default_product = self.env["product.product"].create(
            {"name": "Default Name", "type": "consu"}
        )
        self.env["ir.model.data"].create(
            {
                "module": "sale_shopee",
                "name": "test_xmlid",
                "model": "product.product",
                "res_id": default_product.id,
            }
        )

        self.assertTrue(
            self.shop._get_or_create_matching_product(
                "UNKNOWN_CODE", "test_xmlid", None, None
            )
        )

    def test_get_or_create_matching_product_regen_fallback(self):
        """Test the product search failure with regeneration of the fallback.

        A restored fallback product should be returned when the product is not found.
        """
        self.env["ir.model.data"].create(
            {
                "module": "sale_shopee",
                "name": "test_xmlid",
                "model": "product.product",
            }
        )
        product = self.shop._get_or_create_matching_product(
            "INCORRECT_CODE", "test_xmlid", "Default Name", "consu"
        )

        self.assertRecordValues(
            product,
            [
                {
                    "name": "Default Name",
                    "type": "consu",
                    "list_price": 0,
                    "sale_ok": False,
                    "purchase_ok": False,
                }
            ],
        )

    def test_get_or_create_matching_product_no_fallback(self):
        """Test the product search failure without regeneration of the fallback.

        No product should be returned when product is not found based on internal reference and
        fallback is disabled.
        """
        self.assertFalse(
            self.shop._get_or_create_matching_product(
                "INCORRECT_CODE", "test_xmlid", "Default Name", "consu", fallback=False
            )
        )
        self.assertFalse(
            self.env.ref("sale_shopee.test_xmlid", raise_if_not_found=False)
        )

    def test_get_or_create_matching_product_get_default_shipping(self):
        """Test the product search and get the default shipping product

        No new item should be created when the default code is updated when
        an existing shopee item with the same item_identifier is found
        """
        item_count = self.env["shopee.item"].search_count([])
        product = self.shop._get_or_create_matching_product(
            "non_existing_sku", "shipping_product", "Shopee Shipping", "service"
        )

        self.assertEqual(self.env["shopee.item"].search_count([]), item_count)
        self.assertEqual(product.name, "Shopee Shipping")
        self.assertEqual(product.type, "service")
        self.assertNotEqual(product.default_code, "non_existing_sku")

    # --- Get Pricelist --- #

    def test_get_pricelist_search(self):
        """Test the pricelist search.

        A pricelist should be found with the created currency.
        """
        currency = self.env["res.currency"].create({"name": "TEST", "symbol": "T"})
        self.env["product.pricelist"].create(
            {
                "name": _("Shopee Pricelist %(currency)s", currency=currency.name),
                "active": False,
                "currency_id": currency.id,
            }
        )
        pricelists_count = (
            self.env["product.pricelist"]
            .with_context(active_test=False)
            .search_count([])
        )

        self.assertTrue(self.shop._get_or_create_pricelist(currency))
        self.assertEqual(
            self.env["product.pricelist"]
            .with_context(active_test=False)
            .search_count([]),
            pricelists_count,
        )

    def test_get_pricelist_creation(self):
        """Test the pricelist creation.

        A pricelist should be created when the given currency has no pricelist.
        """
        currency = self.env["res.currency"].create({"name": "TEST", "symbol": "T"})
        pricelists_count = (
            self.env["product.pricelist"]
            .with_context(active_test=False)
            .search_count([])
        )

        pricelist = self.shop._get_or_create_pricelist(currency)

        self.assertEqual(
            self.env["product.pricelist"]
            .with_context(active_test=False)
            .search_count([]),
            pricelists_count + 1,
        )
        self.assertFalse(pricelist.active)
        self.assertEqual(pricelist.currency_id.id, currency.id)

    # --- Get Partner --- #

    def test_get_partners_no_creation_same_partners(self):
        """Test the partners search with contact as delivery.

        No contact should be created.
        """
        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=lambda _shop, operation_, **_kwargs: common.OPERATIONS_RESPONSES_MAP[
                operation_
            ],
        ):
            country_id = (
                self.env["res.country"].search([("code", "=", "VN")], limit=1).id
            )
            self.env["res.partner"].create(
                {
                    "name": "Gederic Frilson",
                    "is_company": True,
                    "street": "123 RainBowMan Street",
                    "street2": "Xã Phong Thạnh Tây B",
                    "zip": "",
                    "city": "New Duck City DC",
                    "country_id": country_id,
                    "state_id": self.env["res.country.state"]
                    .search(
                        [("country_id", "=", country_id), ("name", "=", "Tây Ninh")],
                        limit=1,
                    )
                    .id,
                    "phone_ids": [
                        Command.create({"number": "9876543210", "type": "landline"})
                    ],
                    "customer_rank": 1,
                    "company_id": self.shop.company_id.id,
                    "shopee_buyer_identifier": 444444,
                }
            )
            contacts_count = self.env["res.partner"].search_count([])

            contact, delivery = self.shop._get_or_create_partners_from_data(
                common.ORDER_MOCK
            )

            self.assertEqual(self.env["res.partner"].search_count([]), contacts_count)
            self.assertRecordValues(
                contact,
                [
                    {
                        "id": delivery.id,
                        "type": "contact",
                        "phone_ids": delivery.phone_ids.ids,
                    }
                ],
            )
            self.assertEqual(contact._phone_get_number().number, "9876543210")

    def test_get_partners_no_creation_different_partners(self):
        """Test the partners search with different partners for contact and delivery."""
        country_id = self.env["res.country"].search([("code", "=", "VN")], limit=1).id
        new_partner_vals = {
            "is_company": True,
            "street": "123 RainBowMan Street",
            "street2": "Xã Phong Thạnh Tây B",
            "zip": "",
            "city": "New Duck City DC",
            "country_id": country_id,
            "state_id": self.env["res.country.state"]
            .search(
                [("country_id", "=", country_id), ("name", "=", "Tây Ninh")], limit=1
            )
            .id,
            "phone_ids": [Command.create({"number": "9876543210", "type": "landline"})],
            "customer_rank": 1,
            "company_id": self.shop.company_id.id,
            "shopee_buyer_identifier": 444444,
        }
        contact = self.env["res.partner"].create(
            dict(new_partner_vals, name="Gederic Frilson")
        )
        self.env["res.partner"].create(
            dict(
                new_partner_vals,
                name="Gederic Frilson Delivery",
                type="delivery",
                parent_id=contact.id,
            )
        )
        partners_count = self.env["res.partner"].search_count([])
        order_data = dict(
            common.ORDER_MOCK,
            recipient_address=dict(
                common.BUYER_ADDRESS_MOCK, name="Gederic Frilson Delivery"
            ),
        )

        contact, delivery = self.shop._get_or_create_partners_from_data(order_data)

        self.assertEqual(self.env["res.partner"].search_count([]), partners_count)
        self.assertEqual(delivery.type, "delivery")
        self.assertEqual(delivery.parent_id.id, contact.id)
        self.assertEqual(contact.phone_ids, delivery.phone_ids)
        self.assertNotEqual(contact.id, delivery.id)

    def test_get_partners_creation_delivery(self):
        """Test the partners search with creation of the delivery.

        A delivery partner should be created when a field of the address is not strictly the
        same as that of the contact.
        """
        self.env["res.partner"].create(
            {
                "name": "Gederic Frilson",
                "company_id": self.shop.company_id.id,
                "shopee_buyer_identifier": 444444,
            }
        )
        partners_count = self.env["res.partner"].search_count([])
        contact, delivery = self.shop._get_or_create_partners_from_data(
            common.ORDER_MOCK
        )

        self.assertNotEqual(contact.id, delivery.id)
        self.assertEqual(
            self.env["res.partner"].search_count([]),
            partners_count + 1,
        )

        self.assertRecordValues(
            delivery,
            [
                {
                    "type": "delivery",
                    "parent_id": contact.id,
                    "company_id": self.shop.company_id.id,
                }
            ],
        )

    def test_get_partners_creation_contact(self):
        """Test the partners search with creation of the contact.

        A contact partner should be created when the contact is not found.
        """
        partners_count = self.env["res.partner"].search_count([])

        contact, delivery = self.shop._get_or_create_partners_from_data(
            common.ORDER_MOCK
        )

        self.assertEqual(
            self.env["res.partner"].search_count([]),
            partners_count + 1,
        )

        country_id = self.env["res.country"].search([("code", "=", "VN")], limit=1).id
        state_id = (
            self.env["res.country.state"]
            .search(
                [
                    ("country_id", "=", country_id),
                    ("code", "=", "VN-37"),
                ],
                limit=1,
            )
            .id
        )
        self.assertRecordValues(
            contact,
            [
                {
                    "id": delivery.id,
                    "name": "Gederic Frilson",
                    "type": "contact",
                    "street": "123 RainBowMan Street",
                    "street2": "Xã Phong Thạnh Tây B",
                    "zip": "",
                    "city": "New Duck City DC",
                    "country_id": country_id,
                    "state_id": state_id,
                    "customer_rank": 1,
                    "company_id": self.shop.company_id.id,
                }
            ],
        )
        # Not in the dict above: `assertRecordValues` compares READ values, and
        # a x2many reads back as a list of ids, never as the command list that
        # wrote it. Asserting the ids would be asserting them against
        # themselves, so the number is what gets checked -- as the sibling test
        # two methods down already does.
        self.assertEqual(contact._phone_get_number().number, "9876543210")

    def test_get_partners_creation_contact_delivery(self):
        """Test the partners search with creation of the contact and delivery.

        A contact partner and a delivery partner should be created when the delivery receipt name
        is not the same as the buyer name.
        """
        partners_count = self.env["res.partner"].search_count([])
        order_data = dict(
            common.ORDER_MOCK,
            recipient_address=dict(
                common.BUYER_ADDRESS_MOCK, name="Gederic Frilson Delivery"
            ),
        )

        contact, delivery = self.shop._get_or_create_partners_from_data(order_data)

        self.assertEqual(
            self.env["res.partner"].search_count([]),
            partners_count + 2,
            msg="A contact partner and a delivery partner should be created when the contact "
            "is not found and the name on the order is different from that of the address.",
        )
        self.assertNotEqual(contact.id, delivery.id)
        self.assertRecordValues(
            contact,
            [
                {
                    "type": "contact",
                    "company_id": self.shop.company_id.id,
                    "phone_ids": delivery.phone_ids.ids,
                }
            ],
        )
        self.assertEqual(delivery.type, "delivery")
        self.assertEqual(delivery.parent_id.id, contact.id)

    def test_get_partners_missing_buyer_name(self):
        """Test the partners search with missing buyer name.

        A contact partner should be created when the buyer name is different from the
        contact, even they have the same shopee buyer identifier. The delivery partner
        should be created if the buyer name is different from the shipping address name.
        """
        self.env["res.partner"].create(
            {
                "name": "Gederic Frilson",
                "company_id": self.shop.company_id.id,
                "shopee_buyer_identifier": 444444,
            }
        )
        partners_count = self.env["res.partner"].search_count([])
        order_data = dict(common.ORDER_MOCK, buyer_username=None)

        contact, delivery = self.shop._get_or_create_partners_from_data(order_data)

        self.assertEqual(self.env["res.partner"].search_count([]), partners_count + 2)
        self.assertNotEqual(contact.id, delivery.id)
        self.assertRecordValues(
            contact,
            [
                {
                    "type": "contact",
                    "shopee_buyer_identifier": 444444,
                    "street": "123 RainBowMan Street",
                }
            ],
        )
        self.assertEqual(delivery.type, "delivery")
        self.assertEqual(delivery.parent_id.id, contact.id)

    # --- Find or Create Shopee Item --- #

    def test_find_or_create_item_exist(self):
        """Test the item search of _acquire_item()

        An existing item will be found without creating a new one.
        """
        item_count = self.env["shopee.item"].search_count([])
        item = self.shop._acquire_item("", common.ORDER_ITEM_MOCK["item_id"], "")

        self.assertEqual(self.env["shopee.item"].search_count([]), item_count)
        self.assertEqual(item.id, self.item.id)
        self.assertEqual(item.sync_to_shopee, True)

    def test_find_or_create_item_new_item_product(self):
        """Test the item creation and product restoration of _acquire_item()

        A new item will be created and the default product will be linked.
        """
        item_count = self.env["shopee.item"].search_count([])
        item = self.shop._acquire_item(
            "a_new_sku", "any_item_identifier", "any_model_identifier"
        )

        self.assertEqual(self.env["shopee.item"].search_count([]), item_count + 1)
        self.assertEqual(item.product_id.name, "Shopee Sale")
        self.assertEqual(item.product_id.default_code, False)
        self.assertEqual(item.shopee_item_identifier, "any_item_identifier")
        self.assertEqual(item.shopee_model_identifier, "any_model_identifier")

    def test_find_or_create_item_new_item(self):
        """Test the item creation with no product restoration of _acquire_item()

        A new item will be created and linked to an existing product with the same default code.
        """
        item_count = self.env["shopee.item"].search_count([])
        item = self.shop._acquire_item(
            common.ORDER_ITEM_MOCK["model_sku"], "any_item_identifier", "", "fbs"
        )

        self.assertEqual(self.env["shopee.item"].search_count([]), item_count + 1)

        self.assertEqual(item.product_id.name, self.product.name)
        self.assertEqual(
            item.product_id.default_code, common.ORDER_ITEM_MOCK["model_sku"]
        )
        self.assertRecordValues(
            item,
            [
                {
                    "shopee_item_identifier": "any_item_identifier",
                    "shopee_model_identifier": "",
                    "sync_to_shopee": False,
                }
            ],
        )

    def test_find_or_create_item_change_item_product(self):
        """Test shopee item search and update its linked product of _acquire_item()

        An existing item will be found and its linked product will be changed.
        """
        item_count = self.env["shopee.item"].search_count([])
        default_product = self.env.ref("sale_shopee.default_sale_product")
        self.item.update({"product_id": default_product})
        item = self.shop._acquire_item(
            self.product.default_code,
            common.ORDER_ITEM_MOCK["item_id"],
            common.ORDER_ITEM_MOCK["model_id"],
            "fbs",
        )

        self.assertEqual(
            self.env["shopee.item"].search_count([]),
            item_count,
            "No new item should be created when the default code is changed with the same"
            " item_identifier.",
        )
        self.assertEqual(item.product_id.name, self.product.name)
        self.assertEqual(item.product_id.default_code, self.product.default_code)
        msg = "The correct product should now be assigned to the item."
        self.assertNotEqual(item.product_id, default_product, msg)

    def test_sync_shopee_pickings_with_non_shopee_picking(self):
        """Test calling the shipment label generation on a non Shopee picking doesn't do anything."""
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.env.ref("stock.picking_type_out").id,
                "location_id": self.env.ref("stock.stock_location_stock").id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            }
        )
        picking.action_confirm()
        action_shipping_label = self.env.ref("sale_shopee.action_fetch_shipping_label")
        with patch("odoo.addons.sale_shopee.utils.send_shopee_api_request") as mock_api:
            result = action_shipping_label.with_context(
                active_model="stock.picking", active_ids=picking.ids
            ).run()
            self.assertFalse(
                result,
                msg="Fetching the label of a non-shopee picking shouldn't raise.",
            )
            mock_api.assert_not_called()


@tagged("post_install", "-at_install")
class TestShopeeAuthorizationReturn(common.TestShopeeCommon, HttpCase):
    def setUp(self):
        super().setUp()
        self.authenticate("admin", "admin")

    def _return_path(self, account=None):
        account = account or self.account
        with patch.object(
            type(self.env["ir.egress"]),
            "request",
            return_value=MagicMock(status_code=200),
        ):
            action = self.call_jsonrpc(
                "/web/dataset/call_button",
                {
                    "model": "shopee.account",
                    "method": "action_view_auth_link",
                    "args": [account.ids],
                    "kwargs": {},
                },
            )
        redirect = parse_qs(urlsplit(action["url"]).query)["redirect"][0]
        return urlsplit(redirect).path

    def _return(self, path):
        with (
            patch.object(
                type(self.env["shopee.shop"]),
                "create_or_update_shop",
                autospec=True,
                return_value=self.shop,
            ) as create_or_update,
            mute_logger("odoo.http"),
        ):
            response = self.url_open(
                path, params={"code": "c", "shop_id": "1"}, allow_redirects=False
            )
        return response, create_or_update

    def _assert_refused(self, path):
        response, create_or_update = self._return(path)
        self.assertEqual(response.status_code, 403, response.text)
        create_or_update.assert_not_called()

    def test_the_issued_state_is_accepted_once_for_its_account_and_company(self):
        path = self._return_path()
        response, create_or_update = self._return(path)
        self.assertEqual(response.status_code, 303, response.text)
        create_or_update.assert_called_once()
        self.assertEqual(
            create_or_update.call_args.args[1:3],
            (self.env.company.id, self.account.id),
        )
        self._assert_refused(path)

    def test_an_expired_state_is_refused(self):
        path = self._return_path()
        later = SimpleNamespace(
            time=lambda: (
                time.time() + onboarding._AUTHORIZATION_STATE_MAX_AGE_SECONDS + 1
            )
        )
        with patch.object(security, "time", later):
            self._assert_refused(path)

    def test_a_tampered_state_is_refused(self):
        path = self._return_path()
        prefix, state = path.rsplit("/", 1)
        flipped = state[:-2] + ("A" if state[-2] != "A" else "B") + state[-1]
        for tampered in (flipped, "%C3%A9" * 32, "x"):
            with self.subTest(tampered=tampered):
                self._return_path()
                self._assert_refused(f"{prefix}/{tampered}")

    def test_a_state_from_another_session_is_refused(self):
        path = self._return_path()
        self.authenticate("admin", "admin")
        self._return_path()
        self._assert_refused(path)
