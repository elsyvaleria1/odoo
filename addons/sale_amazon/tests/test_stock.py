from unittest.mock import Mock, patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from odoo.addons.sale_amazon.tests import common
from odoo.addons.stock.tests.common import TestStockCommon


@tagged("post_install", "-at_install")
class TestStock(common.TestAmazonCommon, TestStockCommon):
    def setUp(self):
        super().setUp()

        self.partner = self.env["res.partner"].create({"name": "Gederic Frilson"})
        amazon_offer = self.account._acquire_offer(
            "test SKU", self.account.base_marketplace_id
        )
        self.sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "test",
                            "product_id": self.productA.id,
                            "product_qty": 2,
                            "amazon_item_ref": "123456789",
                            "amazon_offer_id": amazon_offer.id,
                        },
                    )
                ],
                "amazon_order_ref": "123456789",
            }
        )

        self.picking = self.PickingObj.create(
            {
                "picking_type_id": self.picking_type_in.id,
                "location_id": self.supplier_location.id,
                "location_dest_id": self.customer_location.id,
            }
        )
        move_vals = {
            "product_id": self.productA.id,
            "product_uom_qty": 1,
            "product_uom_id": self.productA.uom_id.id,
            "picking_id": self.picking.id,
            "location_id": self.supplier_location.id,
            "location_dest_id": self.customer_location.id,
            "sale_line_id": self.sale_order.line_ids[0].id,
        }
        self.move_1 = self.MoveObj.create(move_vals)
        self.move_2 = self.MoveObj.create(move_vals)
        self.picking.sale_id = self.sale_order.id

    def test_confirm_picking_trigger_SOL_check(self):

        with patch(
            "odoo.addons.sale_amazon.models.stock_picking.StockPicking"
            "._check_sales_order_line_completion",
            new=Mock(),
        ) as mock:
            self.picking.date_done = fields.Datetime.now()
            self.assertEqual(
                mock.call_count,
                1,
                "confirming a picking should trigger a check on the sales "
                "order lines completion",
            )

    def test_check_SOL_completion_no_move(self):

        self.assertIsNone(
            self.picking._check_sales_order_line_completion(),
            "the check of SOL completion should not raise for pickings with completions of 0% (no"
            "confirmed move for a given sales order line)",
        )

    def test_check_SOL_completion_all_moves(self):

        self.move_1.quantity = 1
        self.move_2.quantity = 1
        self.assertIsNone(
            self.picking._check_sales_order_line_completion(),
            "the check of SOL completion should not raise for pickings with completions of 100% "
            "(all moves related to a given sales order line are confirmed)",
        )

    def test_check_SOL_completion_some_moves(self):

        self.move_1.quantity = 1
        with self.assertRaises(UserError):
            self.picking._check_sales_order_line_completion()

    @mute_logger("odoo.addons.sale_amazon.models.amazon_account")
    def test_check_carrier_details_compliance_delivered_for_amazon(self):

        def find_matching_product_mock(
            _self, product_code_, _default_xmlid, default_name_, default_type_
        ):
            product_ = self.env["product.product"].create(
                {
                    "name": default_name_,
                    "type": default_type_,
                    "list_price": 0.0,
                    "sale_ok": False,
                    "purchase_ok": False,
                    "default_code": product_code_,
                }
            )
            product_.product_tmpl_id.taxes_id = [Command.clear()]
            return product_

        with (
            patch(
                "odoo.addons.sale_amazon.utils.send_sp_api_request",
                new=lambda _account, operation, **kwargs: (
                    common.OPERATIONS_RESPONSES_MAP[operation]
                ),
            ),
            patch(
                "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._get_price_from_order_amounts",
                new=lambda self_, subtotal_, *args_, **kwargs_: subtotal_,
            ),
            patch(
                "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._get_or_create_matching_product",
                new=find_matching_product_mock,
            ),
        ):
            self.account._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("amazon_order_ref", "=", "123456789")]
            )
            picking = self.env["stock.picking"].search([("sale_id", "=", order.id)])
            picking.write(
                {
                    "amazon_sync_status": "done",
                    "carrier_id": None,
                    "carrier_tracking_ref": None,
                }
            )
            picking.location_dest_id.usage = "customer"
            picking._check_carrier_details_compliance()

    @mute_logger("odoo.addons.sale_amazon.models.stock_picking")
    @mute_logger("odoo.addons.sale_amazon.models.amazon_account")
    def test_check_carrier_details_compliance_no_carrier(self):

        def find_matching_product_mock(
            _self, product_code_, _default_xmlid, default_name_, default_type_
        ):
            product_ = self.env["product.product"].create(
                {
                    "name": default_name_,
                    "type": default_type_,
                    "list_price": 0.0,
                    "sale_ok": False,
                    "purchase_ok": False,
                    "default_code": product_code_,
                }
            )
            product_.product_tmpl_id.taxes_id = [Command.clear()]
            return product_

        with (
            patch(
                "odoo.addons.sale_amazon.utils.send_sp_api_request",
                new=lambda _account, operation, **kwargs: (
                    common.OPERATIONS_RESPONSES_MAP[operation]
                ),
            ),
            patch(
                "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._get_price_from_order_amounts",
                new=lambda self_, subtotal_, *args_, **kwargs_: subtotal_,
            ),
            patch(
                "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._get_or_create_matching_product",
                new=find_matching_product_mock,
            ),
        ):
            self.account._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("amazon_order_ref", "=", "123456789")]
            )
            picking = self.env["stock.picking"].search([("sale_id", "=", order.id)])
            picking.carrier_id = None
            picking.carrier_tracking_ref = self.tracking_ref
            picking.location_dest_id.usage = "customer"
            with self.assertRaises(UserError):
                picking._check_carrier_details_compliance()

    @mute_logger("odoo.addons.sale_amazon.models.stock_picking")
    @mute_logger("odoo.addons.sale_amazon.models.amazon_account")
    def test_check_carrier_details_compliance_intermediate_delivery_step(self):

        def find_matching_product_mock(
            _self, product_code_, _default_xmlid, default_name_, default_type_
        ):
            product_ = self.env["product.product"].create(
                {
                    "name": default_name_,
                    "type": default_type_,
                    "list_price": 0.0,
                    "sale_ok": False,
                    "purchase_ok": False,
                    "default_code": product_code_,
                }
            )
            product_.product_tmpl_id.taxes_id = [Command.clear()]
            return product_

        with (
            patch(
                "odoo.addons.sale_amazon.utils.send_sp_api_request",
                new=lambda _account, operation, **kwargs: (
                    common.OPERATIONS_RESPONSES_MAP[operation]
                ),
            ),
            patch(
                "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._get_price_from_order_amounts",
                new=lambda self_, subtotal_, *args_, **kwargs_: subtotal_,
            ),
            patch(
                "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._get_or_create_matching_product",
                new=find_matching_product_mock,
            ),
        ):
            self.account._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("amazon_order_ref", "=", "123456789")]
            )
            picking = self.env["stock.picking"].search([("sale_id", "=", order.id)])
            picking.carrier_id = None
            picking.carrier_tracking_ref = self.tracking_ref
            intermediate_destination_id = self.env.ref("stock.location_pack_zone").id
            picking.location_dest_id = intermediate_destination_id
            picking._check_carrier_details_compliance()

    @mute_logger("odoo.addons.sale_amazon.models.stock_picking")
    @mute_logger("odoo.addons.sale_amazon.models.amazon_account")
    def test_check_carrier_details_compliance_no_tracking_number(self):

        def find_matching_product_mock(
            _self, product_code_, _default_xmlid, default_name_, default_type_
        ):
            product_ = self.env["product.product"].create(
                {
                    "name": default_name_,
                    "type": default_type_,
                    "list_price": 0.0,
                    "sale_ok": False,
                    "purchase_ok": False,
                    "default_code": product_code_,
                }
            )
            product_.product_tmpl_id.taxes_id = [Command.clear()]
            return product_

        with (
            patch(
                "odoo.addons.sale_amazon.utils.send_sp_api_request",
                new=lambda _account, operation, **kwargs: (
                    common.OPERATIONS_RESPONSES_MAP[operation]
                ),
            ),
            patch(
                "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._get_price_from_order_amounts",
                new=lambda self_, subtotal_, *args_, **kwargs_: subtotal_,
            ),
            patch(
                "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._get_or_create_matching_product",
                new=find_matching_product_mock,
            ),
        ):
            self.account._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("amazon_order_ref", "=", "123456789")]
            )
            picking = self.env["stock.picking"].search([("sale_id", "=", order.id)])
            picking.carrier_id = self.carrier
            picking.carrier_tracking_ref = None
            with self.assertRaises(UserError):
                picking._check_carrier_details_compliance()

    @mute_logger("odoo.addons.sale_amazon.models.stock_picking")
    @mute_logger("odoo.addons.sale_amazon.models.amazon_account")
    def test_check_carrier_details_compliance_requirements_met_in_last_step_delivery(
        self,
    ):

        def find_matching_product_mock(
            _self, product_code_, _default_xmlid, default_name_, default_type_
        ):
            product_ = self.env["product.product"].create(
                {
                    "name": default_name_,
                    "type": default_type_,
                    "list_price": 0.0,
                    "sale_ok": False,
                    "purchase_ok": False,
                    "default_code": product_code_,
                }
            )
            product_.product_tmpl_id.taxes_id = [Command.clear()]
            return product_

        with (
            patch(
                "odoo.addons.sale_amazon.utils.send_sp_api_request",
                new=lambda _account, operation, **kwargs: (
                    common.OPERATIONS_RESPONSES_MAP[operation]
                ),
            ),
            patch(
                "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._get_price_from_order_amounts",
                new=lambda self_, subtotal_, *args_, **kwargs_: subtotal_,
            ),
            patch(
                "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._get_or_create_matching_product",
                new=find_matching_product_mock,
            ),
        ):
            self.account._sync_orders(auto_commit=False)
            order = self.env["sale.order"].search(
                [("amazon_order_ref", "=", "123456789")]
            )
            picking = self.env["stock.picking"].search([("sale_id", "=", order.id)])
            picking.carrier_id, picking.carrier_tracking_ref = (
                self.carrier,
                self.tracking_ref,
            )
            picking._check_carrier_details_compliance()

    def test_get_carrier_details_returns_carrier_name_when_unsupported(self):
        self.picking.carrier_id = self.carrier
        carrier_name = self.picking._get_formatted_carrier_name()
        self.assertEqual(carrier_name, self.carrier.name)

    def test_get_carrier_details_returns_formatted_carrier_name_when_supported(self):
        self.carrier.name = "d_H l)"
        self.picking.carrier_id = self.carrier
        carrier_name = self.picking._get_formatted_carrier_name()
        self.assertEqual(carrier_name, "DHL")

    def test_sync_orders_confirms_pickings_with_a_pending_status(self):

        def get_sp_api_response_mock(_account, operation_, **_kwargs):
            base_response_ = common.OPERATIONS_RESPONSES_MAP[operation_]
            if operation_ == "getOrder":
                response_ = {"payload": dict(common.ORDER_MOCK, OrderStatus="Shipped")}
            else:
                response_ = base_response_
            return response_

        with patch(
            "odoo.addons.sale_amazon.utils.send_sp_api_request",
            new=get_sp_api_response_mock,
        ):
            self.picking.update({"amazon_sync_status": "error", "state": "cancel"})
            pending_picking = self.PickingObj.create(
                {
                    "picking_type_id": self.picking_type_in.id,
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.customer_location.id,
                }
            )
            move_vals = {
                "product_id": self.productA.id,
                "product_uom_qty": 1,
                "product_uom_id": self.productA.uom_id.id,
                "picking_id": pending_picking.id,
                "location_id": self.supplier_location.id,
                "location_dest_id": self.customer_location.id,
                "sale_line_id": self.sale_order.line_ids[0].id,
            }
            self.MoveObj.create(move_vals)
            pending_picking.sale_id = self.sale_order.id

            self.account._sync_order_by_reference(self.sale_order.amazon_order_ref)
            self.assertEqual(
                self.picking.amazon_sync_status,
                "error",
                msg="Picking with an errored Amazon sync status should not be updated when there is"
                "another pending picking and the picking is confirmed by Amazon.",
            )
            self.assertEqual(
                pending_picking.amazon_sync_status,
                "done",
                msg="Picking with a pending Amazon sync status should be updated when the picking "
                "is confirmed by Amazon.",
            )

    def test_sync_orders_confirms_pickings_with_an_errored_status(self):

        def get_sp_api_response_mock(_account, operation_, **_kwargs):
            base_response_ = common.OPERATIONS_RESPONSES_MAP[operation_]
            if operation_ == "getOrder":
                response_ = {"payload": dict(common.ORDER_MOCK, OrderStatus="Shipped")}
            else:
                response_ = base_response_
            return response_

        with patch(
            "odoo.addons.sale_amazon.utils.send_sp_api_request",
            new=get_sp_api_response_mock,
        ):
            self.picking.update({"amazon_sync_status": "error"})

            self.account._sync_order_by_reference(self.sale_order.amazon_order_ref)
            self.assertEqual(
                self.picking.amazon_sync_status,
                "done",
                msg="Picking with an errored Amazon sync status should be updated when the picking "
                "is confirmed by Amazon and there is no pending picking.",
            )

    @mute_logger("odoo.addons.sale_amazon.models.amazon_account")
    def test_action_retry_amazon_sync_dont_resync_when_picking_is_confirmed_from_amazon(
        self,
    ):

        self.picking.amazon_sync_status = "error"

        with patch(
            "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._sync_order_by_reference",
            new=lambda self_, *args_: self.picking.update(
                {"amazon_sync_status": "done"}
            ),
        ):
            self.picking.action_retry_amazon_sync()
        msg = "Picking with Amazon sync status updated during the sync order should stay as done."
        self.assertEqual(self.picking.amazon_sync_status, "done", msg=msg)

    def test_action_retry_amazon_sync_set_waiting_state_after_resync(self):
        self.env.company.partner_id.write(
            {
                "street": "Company Street Office 2",
                "country_id": self.env.ref("base.be").id,
            }
        )
        self.picking.amazon_sync_status = "error"
        with (
            patch(
                "odoo.addons.sale_amazon.models.amazon_account.AmazonAccount._sync_order_by_reference",
            ),
            patch(
                "odoo.addons.sale_amazon.utils.submit_feed", return_value="Mock feed ID"
            ),
        ):
            self.picking.action_retry_amazon_sync()
        msg = "Picking with Amazon sync status not updated in the sync order should be re-submitted"
        self.assertEqual(self.picking.amazon_sync_status, "processing", msg=msg)
        msg = "Picking re-submitted have the new feed ID set."
        self.assertEqual(self.picking.amazon_feed_ref, "Mock feed ID", msg=msg)

    def test_generate_stock_moves_for_not_tracked_product_sets_move_done(self):
        self.product.tracking = "none"
        self.env["stock.quant"].create(
            {
                "product_id": self.product.id,
                "location_id": self.stock_location.id,
                "quantity": 30,
            }
        )
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "amazon_item_ref": "item_ref",
                            "product_qty": 2,
                        }
                    )
                ],
                "amazon_order_ref": "test_ref",
                "state": "done",
                "locked": True,
            }
        )
        StockMove = self.env["stock.move"]
        initial_moves = StockMove.search([("product_id", "=", self.product.id)])
        self.assertFalse(initial_moves, msg="No stock move should be created yet.")

        self.account._create_stock_moves(sale_order)

        new_moves = StockMove.search(
            [("product_id", "=", self.product.id), ("id", "not in", initial_moves.ids)]
        )

        msg = "All moves should be set as done."
        self.assertEqual(new_moves.state, "done", msg=msg)
