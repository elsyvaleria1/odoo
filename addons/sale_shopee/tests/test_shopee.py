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

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_orders_full(self):
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
            self.assertEqual(len(order_lines), 1)
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

        def get_shopee_api_response_mock(_shop, operation_, *_args):
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

        def get_shopee_api_response_mock(_shop, operation_, *_args):
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

        def get_shopee_api_response_mock(_shop, operation_, *_args):
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
            self.shop._sync_orders(auto_commit=False)
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

        def get_shopee_api_response_mock(_shop, operation_, *_args):
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
            order_count = self.env["sale.order"].search_count([])
            self.order_created = False
            self.shop._sync_orders(auto_commit=False)
            self.assertEqual(self.env["sale.order"].search_count([]), order_count + 1)

            self.shop.last_orders_sync_date = datetime.fromtimestamp(
                1579050000
            )

            self.order_created = True
            self.shop._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("shopee_order_ref", "=", "O123456789")]
            )
            self.assertEqual(order.state, "cancel")

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_orders_cancel_abort(self):

        def get_shopee_api_response_mock(_shop, operation_, *_args):
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
            self.order_cancelled = False
            self.shop._sync_orders(auto_commit=False)

            self.shop.last_orders_sync_date = datetime.fromtimestamp(
                1579050000
            )

            order = self.env["sale.order"].search(
                [("shopee_order_ref", "=", common.ORDER_SN_MOCK)]
            )
            self.assertNotEqual(order.state, "shipped")
            picking = self.env["stock.picking"].search([("sale_id", "=", order.id)])
            self.order_cancelled = True

            self.shop._sync_orders(auto_commit=False)

            self.assertEqual(order.state, "cancel")
            self.assertEqual(picking.state, "cancel")


    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_inventory(self):

        def get_shopee_api_response_mock(
            _shop, operation_, _params="", body="", _files="", method="GET"
        ):
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

        def get_shopee_api_response_mock(_shop, operation_, *_args):
            if operation_ == "update_stock":
                raise AssertionError("the inventory must not be sent to Shopee")
            return common.OPERATIONS_RESPONSES_MAP[operation_]

        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=get_shopee_api_response_mock,
        ):
            self.shop.synchronize_inventory = False
            self.assertEqual(self.shop.shopee_item_ids, self.item)

            self.shop._sync_inventory(auto_commit=False)

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_inventory_error(self):

        class SyncFailureReportedError(Exception):
            pass

        def get_shopee_api_response_mock(_shop, operation_, *_args, **_kwargs):
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


    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_pickings(self):
        with patch(
            "odoo.addons.sale_shopee.utils.send_shopee_api_request",
            new=lambda _shop, operation_, *_args, **_kwargs: (
                common.OPERATIONS_RESPONSES_MAP[operation_]
            ),
        ):
            self.shop._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("shopee_order_ref", "=", "O123456789")]
            )
            picking = self.env["stock.picking"].search([("sale_id", "=", order.id)])

            self.assertEqual(len(picking), 1)
            self.assertEqual(picking.carrier_id.name, "Fake Ship")
            self.assertEqual(picking.shopee_label_status, "not available")
            self.assertEqual(len(picking.message_ids.attachment_ids), 0)

            picking._action_done()
            self.env["stock.picking"]._sync_shopee_pickings(
                tuple(self.shop.ids), auto_commit=False
            )

            self.assertEqual(picking.shopee_label_status, "stored")
            self.assertEqual(picking.carrier_tracking_ref, "MY200448706479IT")
            self.assertEqual(len(picking.message_ids.attachment_ids), 1)

    @mute_logger("odoo.addons.sale_shopee.models.shopee_shop")
    def test_sync_pickings_processing(self):

        def get_shopee_api_response_mock(_shop, operation_, *_args, **_kwargs):
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


    def test_get_or_create_matching_product_search(self):
        product = self.shop._get_or_create_matching_product(
            common.ORDER_ITEM_MOCK["model_sku"], None, None, None
        )
        self.assertEqual(product.name, self.item.product_id.name)
        self.assertEqual(product.default_code, common.ORDER_ITEM_MOCK["model_sku"])

    def test_get_or_create_matching_product_use_fallback(self):
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
        self.assertFalse(
            self.shop._get_or_create_matching_product(
                "INCORRECT_CODE", "test_xmlid", "Default Name", "consu", fallback=False
            )
        )
        self.assertFalse(
            self.env.ref("sale_shopee.test_xmlid", raise_if_not_found=False)
        )

    def test_get_or_create_matching_product_get_default_shipping(self):
        item_count = self.env["shopee.item"].search_count([])
        product = self.shop._get_or_create_matching_product(
            "non_existing_sku", "shipping_product", "Shopee Shipping", "service"
        )

        self.assertEqual(self.env["shopee.item"].search_count([]), item_count)
        self.assertEqual(product.name, "Shopee Shipping")
        self.assertEqual(product.type, "service")
        self.assertNotEqual(product.default_code, "non_existing_sku")


    def test_get_pricelist_search(self):
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


    def test_get_partners_no_creation_same_partners(self):
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
        self.assertEqual(contact._phone_get_number().number, "9876543210")

    def test_get_partners_creation_contact_delivery(self):
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


    def test_find_or_create_item_exist(self):
        item_count = self.env["shopee.item"].search_count([])
        item = self.shop._acquire_item("", common.ORDER_ITEM_MOCK["item_id"], "")

        self.assertEqual(self.env["shopee.item"].search_count([]), item_count)
        self.assertEqual(item.id, self.item.id)
        self.assertEqual(item.sync_to_shopee, True)

    def test_find_or_create_item_new_item_product(self):
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
