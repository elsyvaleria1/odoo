import time
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from odoo import fields
from odoo.libs.json import loads as json_loads
from odoo.tests.common import HttpCase, freeze_time, tagged
from odoo.tools import hmac, mute_logger

from odoo.addons.sale_lazada import const
from odoo.addons.sale_lazada import utils as lazada_utils
from odoo.addons.sale_lazada.tests import common


@tagged("post_install", "-at_install")
@freeze_time("2020-02-01")
class TestLazada(common.TestLazadaCommon):
    def test_the_authorization_link_carries_an_encoded_query(self):
        with patch.object(lazada_utils, "get_public_sign", return_value="sign"):
            url = self.shop.action_view_auth_link()["url"]

        split = urlsplit(url)
        self.assertEqual(f"{split.scheme}://{split.netloc}{split.path}", const.AUTH_URL)
        query = parse_qs(split.query, strict_parsing=True)
        self.assertEqual(query["client_id"], ["1"])
        self.assertEqual(query["state"], [self.shop.lazada_oauth_state])
        self.assertTrue(
            query["redirect_uri"][0].startswith(
                f"{self.shop.get_base_url()}/lazada/return_from_authorization/{self.shop.id}/"
            )
        )
        self.assertTrue(query["redirect_uri"][0].endswith("/sign"))

    @mute_logger("odoo.addons.sale_lazada.models.lazada_shop")
    def test_sync_orders_full(self):
        with (
            patch(
                "odoo.addons.sale_lazada.utils.send_lazada_api_request",
                new=lambda operation, _shop, *_args, **_kwargs: (
                    common.OPERATIONS_RESPONSES_MAP[operation]
                ),
            ),
            patch(
                "odoo.addons.sale_lazada.models.lazada_shop.LazadaShop._get_price_from_tax_included_total",
                new=lambda _self, subtotal_, *_args, **_kwargs: subtotal_,
            ),
        ):
            self.shop._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("lazada_order_ref", "=", common.ORDER_ID_MOCK)]
            )
            product_line = order.line_ids.filtered(
                lambda line: line.product_id.default_code == "TEST-SKU-001"
            )

            self.assertEqual(
                self.shop.last_orders_sync_date,
                fields.Datetime.now(),
                msg="The last_orders_sync_date should be equal to current datetime after a"
                " successful run",
            )
            self.assertEqual(len(order), 1, msg="An order should be created")
            self.assertRecordValues(
                order,
                [
                    {
                        "date_order": datetime(2020, 1, 15),
                        "company_id": self.shop.company_id.id,
                        "user_id": self.shop.user_id.id,
                        "team_id": self.shop.team_id.id,
                        "lazada_fulfillment_type": "fbm",
                    }
                ],
            )
            self.assertRecordValues(
                product_line,
                [
                    {
                        "price_unit": 100.0,
                        "discount": 20.0,
                        "product_qty": 1.0,
                        "product_id": self.product.id,
                    }
                ],
            )

    @mute_logger("odoo.addons.sale_lazada.models.lazada_shop")
    def test_sync_orders_partial(self):

        def get_lazada_api_response_mock(operation_, _shop, *_args, **_kwargs):
            if operation_ == "GetOrders":
                self.api_call_count += 1
                if self.api_call_count == 2:
                    raise lazada_utils.LazadaRateLimitError(operation_)
                return common.GET_ORDERS_RESPONSE_MOCK
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_lazada.utils.send_lazada_api_request",
            new=get_lazada_api_response_mock,
        ):
            self.api_call_count = 0

            self.shop._sync_orders(auto_commit=False)

            orders = self.env["sale.order"].search(
                [("lazada_order_ref", "=", str(common.ORDER_ID_MOCK))]
            )
            self.assertEqual(
                len(orders), 1, msg="Only one order should be synchronized"
            )
            self.assertEqual(
                self.shop.last_orders_sync_date,
                self.initial_sync_date + timedelta(days=const.ORDER_LIST_DAYS_LIMIT),
                msg="The last_orders_sync_date should be equal to the LastUpdateDate of the last"
                " fully synchronized period.",
            )
            self.assertEqual(self.api_call_count, 2)

    @mute_logger("odoo.addons.sale_lazada.models.lazada_shop")
    def test_sync_orders_fail(self):

        def get_lazada_api_response_mock(operation_, _shop, *_args, **_kwargs):
            self.api_call_count += 1
            if operation_ == "GetOrders":
                raise lazada_utils.LazadaRateLimitError(operation_)
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_lazada.utils.send_lazada_api_request",
            new=get_lazada_api_response_mock,
        ):
            self.api_call_count = 0
            last_orders_sync_date_copy = self.shop.last_orders_sync_date

            self.shop._sync_orders(auto_commit=False)

            self.assertEqual(self.api_call_count, 1)
            self.assertEqual(
                self.shop.last_orders_sync_date, last_orders_sync_date_copy
            )

    @mute_logger("odoo.addons.sale_lazada.models.lazada_shop")
    def test_sync_orders_no_active_shop(self):

        def get_lazada_api_response_mock(operation_, _shop, *_args, **_kwargs):
            self.api_call_count += 1
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_lazada.utils.send_lazada_api_request",
            new=get_lazada_api_response_mock,
        ):
            self.api_call_count = 0
            last_orders_sync_date_copy = self.shop.last_orders_sync_date
            self.shop.write({"active": False})

            self.env["lazada.shop"]._sync_orders(auto_commit=False)

            self.assertEqual(self.api_call_count, 0)
            self.assertEqual(
                self.shop.last_orders_sync_date, last_orders_sync_date_copy
            )

    @mute_logger("odoo.addons.sale_lazada.models.lazada_shop")
    def test_sync_orders_fbl(self):

        def get_lazada_api_response_mock(operation_, _shop, *_args, **_kwargs):
            if operation_ == "GetOrders":
                return {
                    **common.GET_ORDERS_RESPONSE_MOCK,
                    "data": {
                        "orders": [{**common.ORDER_MOCK, "statuses": ["confirmed"]}]
                    },
                }
            if operation_ == "GetMultipleOrderItems":
                return {
                    **common.GET_ORDER_ITEMS_RESPONSE_MOCK,
                    "data": [
                        {
                            "order_id": common.ORDER_ID_MOCK,
                            "order_number": common.ORDER_ID_MOCK,
                            "order_items": [
                                {
                                    **common.ORDER_ITEM_MOCK,
                                    "is_fbl": 1,
                                    "status": "confirmed",
                                }
                            ],
                        }
                    ],
                }
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_lazada.utils.send_lazada_api_request",
            new=get_lazada_api_response_mock,
        ):
            self.shop._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("lazada_order_ref", "=", common.ORDER_ID_MOCK)]
            )

            self.assertEqual(len(order), 1)
            self.assertEqual(order.lazada_fulfillment_type, "fbl")
            self.assertEqual(len(order.line_ids), 1)
            self.assertEqual(
                order.warehouse_id,
                self.shop.fbl_location_id.warehouse_id,
                "FBL orders should use the FBL location's warehouse",
            )

    @mute_logger("odoo.addons.sale_lazada.models.lazada_shop")
    def test_sync_orders_cancel(self):

        def get_lazada_api_response(operation_, _shop, _params=None, **_kwargs):
            if operation_ == "GetOrders":
                statuses = ["pending"] if not self.order_canceled else ["canceled"]
                return {
                    "code": "0",
                    "request_id": "0_sync_orders_cancel",
                    "data": {
                        "countTotal": 1,
                        "count": 1,
                        "orders": [{**common.ORDER_MOCK, "statuses": statuses}],
                    },
                }
            if operation_ == "GetMultipleOrderItems":
                status = "pending" if not self.order_canceled else "canceled"
                return {
                    "code": "0",
                    "request_id": "0_sync_orders_cancel_items",
                    "data": [
                        {
                            "order_id": common.ORDER_ID_MOCK,
                            "order_number": common.ORDER_ID_MOCK,
                            "order_items": [
                                {**common.ORDER_ITEM_MOCK, "status": status}
                            ],
                        }
                    ],
                }
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with (
            patch(
                "odoo.addons.sale_lazada.utils.send_lazada_api_request",
                new=get_lazada_api_response,
            ),
            patch(
                "odoo.addons.sale_lazada.models.lazada_shop.LazadaShop._get_price_from_tax_included_total",
                new=lambda _self, subtotal_, *_args, **_kwargs: subtotal_,
            ),
        ):
            self.order_canceled = False

            self.shop._sync_orders(auto_commit=False)

            order = self.env["sale.order"].search(
                [("lazada_order_ref", "=", common.ORDER_MOCK["order_id"])]
            )
            self.assertEqual(
                len(order), 1, "Order should be created before cancellation."
            )
            self.order_canceled = True

            with freeze_time("2020-03-01"):
                self.shop._sync_orders(auto_commit=False)

            self.assertEqual(
                order.state, "cancel", "Canceled orders should be canceled in Odoo."
            )
            self.assertEqual(
                order.picking_ids.move_ids[0].product_uom_qty,
                0,
                "The product quantity should be 0 after cancellation.",
            )
            self.assertTrue(
                all(
                    item.status == "canceled"
                    for item in order.line_ids.lazada_order_item_ids
                ),
                "All Lazada order items should be marked as canceled.",
            )

    @mute_logger("odoo.addons.sale_lazada.models.lazada_shop")
    def test_sync_inventory(self):

        def get_lazada_api_response_mock(operation_, _shop, params=None, **_kwargs):
            if operation_ == "UpdateSellableQuantity":
                self.payload = json_loads(params["payload"])
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_lazada.utils.send_lazada_api_request",
            new=get_lazada_api_response_mock,
        ):
            self.shop.synchronize_inventory = True
            self.env["stock.quant"]._update_available_quantity(
                self.product, self.shop.fbm_warehouse_id.lot_stock_id, 100
            )

            self.shop._sync_inventory(auto_commit=False)

            item_payload = self.payload["Request"]["Product"]["Skus"]["Sku"][0]
            self.assertEqual(
                item_payload["SkuId"], str(common.ORDER_ITEM_MOCK["sku_id"])
            )
            self.assertEqual(item_payload["SellableQuantity"], 100)

    @mute_logger("odoo.addons.sale_lazada.models.lazada_shop")
    def test_sync_inventory_is_skipped_when_disabled(self):

        def get_lazada_api_response_mock(operation_, _shop, *_args, **_kwargs):
            self.api_call_count += 1
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_lazada.utils.send_lazada_api_request",
            new=get_lazada_api_response_mock,
        ):
            self.api_call_count = 0
            self.shop.synchronize_inventory = False
            self.shop._sync_inventory(auto_commit=False)
            self.assertEqual(self.api_call_count, 0)

    @mute_logger("odoo.addons.sale_lazada.models.lazada_shop")
    def test_sync_product_catalog_initialization(self):

        def get_lazada_api_response_mock(
            operation_, _shop, params_=None, *_args, **_kwargs
        ):
            params_ = params_ or {}
            if operation_ == "GetProducts":
                self.time_from = params_.get("update_after")
                self.time_to = params_.get("update_before")
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_lazada.utils.send_lazada_api_request",
            new=get_lazada_api_response_mock,
        ):
            self.shop.last_product_catalog_sync_date = None
            self.shop.lazada_item_ids = self.env["lazada.item"]
            self.assertEqual(len(self.shop.lazada_item_ids), 0)

            self.shop._sync_product_catalog()

            self.assertEqual(len(self.shop.lazada_item_ids), 1)
            self.assertEqual(
                self.shop.lazada_item_ids.lazada_item_extern_id,
                common.ORDER_ITEM_MOCK["sku_id"],
            )
            self.assertEqual(
                self.shop.lazada_item_ids.product_id.default_code, "TEST-SKU-001"
            )
            self.assertTrue(self.shop.lazada_item_ids.sync_lazada_inventory)

            self.assertEqual(self.time_from, None)
            self.assertEqual(self.time_to, None)

            self.assertEqual(
                self.shop.last_product_catalog_sync_date, datetime(2020, 2, 1)
            )

    @mute_logger("odoo.addons.sale_lazada.models.lazada_shop")
    def test_sync_product_catalog_update(self):

        def get_lazada_api_response_mock(
            operation_, _shop, params=None, *_args, **_kwargs
        ):
            if operation_ == "GetProducts":
                params = params or {}
                self.time_from = params.get("update_after")
                self.time_to = params.get("update_before")
                return {
                    **common.GET_PRODUCTS_RESPONSE_MOCK,
                    "data": {
                        "total_products": 1,
                        "products": [
                            {
                                "item_id": 2222222222,
                                "status": "Active",
                                "skus": [
                                    {
                                        "SellerSku": "TEST-SKU-002",
                                        "Status": "active",
                                        "SkuId": 10002,
                                        "fblWarehouseInventories": [],
                                    }
                                ],
                            }
                        ],
                    },
                }
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_lazada.utils.send_lazada_api_request",
            new=get_lazada_api_response_mock,
        ):
            self.env["product.product"].create(
                {
                    "name": "Test Product 2",
                    "type": "consu",
                    "default_code": "TEST-SKU-002",
                    "list_price": 100.0,
                    "is_storable": True,
                    "tracking": "none",
                    "taxes_id": [],
                }
            )
            self.assertEqual(
                self.shop.last_product_catalog_sync_date, self.initial_sync_date
            )

            self.shop._sync_product_catalog()

            self.assertEqual(len(self.shop.lazada_item_ids), 2)
            item = self.shop.lazada_item_ids.filtered(
                lambda i: i.lazada_item_extern_id == "10002"
            )
            self.assertTrue(item)
            self.assertTrue(item.sync_lazada_inventory)

            self.assertEqual(self.time_from, "2020-01-01T07:00:00+07:00")
            self.assertEqual(self.time_to, "2020-02-01T07:00:00+07:00")

            updated_sync_date = lazada_utils.lazada_timestamp_to_datetime(
                "2020-02-01T07:00:00+07:00"
            )
            self.assertEqual(
                self.shop.last_product_catalog_sync_date, updated_sync_date
            )

    def test_get_or_create_matching_product(self):
        found_product = self.shop._get_or_create_matching_product(
            "TEST-SKU-001", "default_shipping", "Default Shipping", "service"
        )
        self.assertEqual(found_product.id, self.product.id)

        found_product = self.shop._get_or_create_matching_product(
            "NONEXISTENT-SKU",
            "default_shipping",
            "Default Shipping",
            "service",
            fallback=False,
        )
        self.assertFalse(found_product)

    def test_find_or_create_item(self):
        found_item = self.shop._acquire_item(
            "TEST-SKU-001", common.ORDER_ITEM_MOCK["sku_id"], "fbm"
        )
        self.assertEqual(found_item.id, self.item.id)
        self.assertTrue(
            found_item.sync_lazada_inventory,
            "Existing FBM item with storable product should be marked for synchronization.",
        )

        refreshed = self.shop._acquire_item(
            "UPDATED-SKU", common.ORDER_ITEM_MOCK["sku_id"], "fbl"
        )
        self.assertEqual(refreshed, self.item)
        self.assertEqual(refreshed.lazada_sku, "UPDATED-SKU")
        self.assertEqual(refreshed.fulfillment_type, "fbl")
        self.assertEqual(refreshed.product_id, self.product)

        new_item = self.shop._acquire_item("NEW-SKU-001", 98765, "fbm")
        self.assertNotEqual(new_item.id, self.item.id)
        self.assertFalse(
            new_item.sync_lazada_inventory,
            "Non-storable products should not be marked for synchronization.",
        )

    def test_find_or_create_partners_from_data(self):
        with patch(
            "odoo.addons.sale_lazada.models.lazada_shop.LazadaShop._get_or_create_matching_product",
            new=lambda _self, _sku, _default_xmlid, _default_name, _default_type, _fallback=True: (
                self.product
            ),
        ):
            order_data = dict(common.ORDER_MOCK)
            order_data["order_items"] = [common.ORDER_ITEM_MOCK]
            partner_shipping, partner_invoice = (
                self.shop._get_or_create_partners_from_data(order_data)
            )

            self.assertTrue(partner_shipping)
            self.assertTrue(partner_invoice)
            self.assertEqual(partner_shipping.name, "Gederic Frilson")
            self.assertEqual(partner_shipping.country_id.code, "VN")
            self.assertEqual(partner_shipping.lazada_buyer_extern_id, "30001")
            self.assertEqual(partner_shipping.street, "123 RainBowMan Street")
            self.assertEqual(partner_shipping.street2, "Apartment 4B")
            self.assertEqual(partner_shipping.zip, "12345")
            self.assertEqual(partner_shipping.city, "New Duck City")
            self.assertEqual(
                partner_shipping._phone_get_number().number, "+1 234-567-8910"
            )

    def test_compute_lazada_order_status(self):
        order_data = dict(common.ORDER_MOCK)
        order_data["order_items"] = [dict(common.ORDER_ITEM_MOCK)]
        order = self.shop._create_order_from_data(order_data)

        order.line_ids.lazada_order_item_ids.status = "processing"

        self.assertEqual(order.lazada_order_status, "processing")

        self.env["lazada.order.item"].create(
            {
                "order_item_extern_id": 456,
                "sale_order_line_id": order.line_ids.id,
                "stock_move_id": order.line_ids.move_ids[0].id,
                "status": "delivered",
            }
        )

        self.assertEqual(order.lazada_order_status, "manual")

    def test_get_lazada_aggregated_status_single_status(self):
        status = lazada_utils.get_lazada_aggregated_status(["processing"])
        self.assertEqual(status, "processing")

    def test_get_lazada_aggregated_status_mixed_statuses(self):
        status = lazada_utils.get_lazada_aggregated_status(["processing", "delivered"])
        self.assertEqual(status, "manual")

    def test_get_lazada_aggregated_status_canceled_and_other(self):
        status = lazada_utils.get_lazada_aggregated_status(["processing", "canceled"])
        self.assertEqual(status, "processing")

    def test_get_lazada_aggregated_status_all_canceled(self):
        status = lazada_utils.get_lazada_aggregated_status(["canceled"])
        self.assertEqual(status, "canceled")

    def test_should_create_fbm_order_with_pending_status(self):
        order_data_fbm_pending = {
            "order_items": [
                {**common.ORDER_ITEM_MOCK, "shipping_provider_type": "standard"}
            ],
            "statuses": ["pending"],
        }
        self.assertTrue(
            self.shop._is_order_creation_required(order_data_fbm_pending, "fbm"),
            "FBM orders with 'pending' status should be synchronized.",
        )

    def test_should_not_create_fbm_order_with_confirmed_status(self):
        order_data_fbm_confirmed = {
            "order_items": [
                {**common.ORDER_ITEM_MOCK, "shipping_provider_type": "standard"}
            ],
            "statuses": ["confirmed"],
        }
        self.assertFalse(
            self.shop._is_order_creation_required(order_data_fbm_confirmed, "fbm"),
            "FBM orders without 'pending' status should be ignored.",
        )

    def test_should_create_fbl_order_with_confirmed_status(self):
        order_data_fbl_confirmed = {
            "order_items": [
                {
                    **common.ORDER_ITEM_MOCK,
                    "shipping_provider_type": "standard",
                    "is_fbl": 1,
                }
            ],
            "statuses": ["confirmed"],
        }
        self.assertTrue(
            self.shop._is_order_creation_required(order_data_fbl_confirmed, "fbl"),
            "FBL orders with 'confirmed' status should be synchronized.",
        )

    def test_should_not_create_fbl_order_with_pending_status(self):
        order_data_fbl_pending = {
            "order_items": [
                {
                    **common.ORDER_ITEM_MOCK,
                    "shipping_provider_type": "standard",
                    "is_fbl": 1,
                }
            ],
            "statuses": ["pending"],
        }
        self.assertFalse(
            self.shop._is_order_creation_required(order_data_fbl_pending, "fbl"),
            "FBL orders without 'confirmed' status should be ignored.",
        )

    def test_get_fulfillment_type_fbm(self):
        fbm_order_data = {
            "order_id": "TESTFBM",
            "order_items": [{**common.ORDER_ITEM_MOCK, "is_fbl": 0}],
        }
        self.assertEqual(self.shop._get_fulfillment_type(fbm_order_data), "fbm")

    def test_get_fulfillment_type_fbl(self):
        fbl_order_data = {
            "order_id": "TESTFBL",
            "order_items": [{**common.ORDER_ITEM_MOCK, "is_fbl": 1}],
        }
        self.assertEqual(self.shop._get_fulfillment_type(fbl_order_data), "fbl")

    def test_get_fulfillment_type_mixed(self):
        mixed_order_data = {
            "order_id": "TESTMIX",
            "order_items": [
                {**common.ORDER_ITEM_MOCK, "is_fbl": 0},
                {**common.ORDER_ITEM_MOCK, "is_fbl": 1},
            ],
        }
        self.assertIsNone(self.shop._get_fulfillment_type(mixed_order_data))


@tagged("post_install", "-at_install")
class TestLazadaAuthorizationReturn(common.TestLazadaCommon, HttpCase):
    def setUp(self):
        super().setUp()
        self.authenticate("admin", "admin")
        self.timestamp = int(time.time())
        self.sign = hmac(
            self.env(su=True),
            lazada_utils.AUTHORIZATION_SCOPE,
            f"{self.shop.id}|{self.timestamp}",
        )

    def _return(self, sign, **params):
        with patch.object(
            type(self.env["lazada.shop"]), "_prepare_shop_vals", return_value={}
        ) as prepare:
            response = self.url_open(
                f"/lazada/return_from_authorization/{self.shop.id}/{self.timestamp}/"
                f"{sign}",
                params={"code": "c", **params},
                allow_redirects=False,
            )
        return response, prepare

    @mute_logger("odoo.http")
    def test_a_non_ascii_sign_or_state_is_refused(self):
        self.shop.lazada_oauth_state = "the-state"
        for sign, state in (("%C3%A9" * 32, "the-state"), (self.sign, "é" * 9)):
            with self.subTest(sign=sign, state=state):
                response, prepare = self._return(sign, state=state)
                self.assertEqual(response.status_code, 403)
                prepare.assert_not_called()

    @mute_logger("odoo.http")
    def test_a_replayed_return_without_state_is_refused_once_the_state_is_spent(self):
        self.shop.lazada_oauth_state = False
        response, prepare = self._return(self.sign)
        self.assertEqual(response.status_code, 403)
        prepare.assert_not_called()

    def test_the_matching_state_is_accepted_and_spent(self):
        self.shop.lazada_oauth_state = "the-state"
        with patch.object(
            lazada_utils,
            "send_lazada_api_request",
            return_value={"data": {"name": "mock_lazada_shop"}},
        ):
            response, prepare = self._return(self.sign, state="the-state")
        self.assertEqual(response.status_code, 303)
        prepare.assert_called_once_with("c")
        self.assertFalse(self.shop.lazada_oauth_state)
