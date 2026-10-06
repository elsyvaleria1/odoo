from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import archive_maintenance_approval_categories


@tagged("post_install", "-at_install")
class TestMaintenanceAccess(TransactionCase):
    """Who may reach a maintenance plan, and through which flow.

    The ACLs here once granted base.group_user read/write/create on product.trace
    and write on product.template, so any employee could rewrite an asset's
    value. Narrowing them is easy to get wrong in the other direction: the
    plan appears on the *vanilla* lot form, and closing a maintenance return
    rearms the plan.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        archive_maintenance_approval_categories(cls.env)
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.warehouse.allow_maintenance = True
        cls.template = cls.env["product.template"].create(
            {
                "name": "Access probe machine",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("resource_asset.kind_machinery").id,
                "maintenance_ok": True,
            }
        )
        cls.lot = cls.env["product.trace"].create(
            {"name": "ACCESS-1", "product_id": cls.template.product_variant_ids[0].id}
        )
        cls.plan = cls.env["maintenance.plan"].create(
            {
                "asset_id": cls.lot.asset_id.id,
                "repeat_interval": 1,
                "repeat_unit": "month",
            }
        )
        cls.warehouse_user = cls.env["res.users"].create(
            {
                "name": "Warehouse only",
                "login": "maint_access_warehouse",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("stock.group_stock_user").id,
                        ],
                    )
                ],
            }
        )
        cls.plain_user = cls.env["res.users"].create(
            {
                "name": "Plain employee",
                "login": "maint_access_plain",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def test_an_employee_cannot_reach_assets_through_this_module(self):
        with self.assertRaises(AccessError):
            self.lot.with_user(self.plain_user).read(["name"])

    def test_an_employee_cannot_rewrite_a_product_template(self):
        with self.assertRaises(AccessError):
            self.template.with_user(self.plain_user).write({"name": "Renamed"})

    def test_a_warehouse_user_can_open_a_lot_that_has_a_plan(self):
        """A plan is the asset's, and a warehouse user reaches it through the
        serial they own."""
        data = self.lot.asset_id.with_user(self.warehouse_user).read(
            ["name", "maintenance_plan_ids", "maintenance_plan_count"]
        )
        self.assertEqual(data[0]["maintenance_plan_ids"], self.plan.ids)

    def test_a_warehouse_user_cannot_edit_a_plan(self):
        with self.assertRaises(AccessError):
            self.plan.with_user(self.warehouse_user).write({"repeat_interval": 9})

    def test_closing_a_maintenance_return_rearms_the_plan_for_a_warehouse_user(self):
        """Rearming is a consequence of the transfer, not an edit by its validator."""
        product = self.template.product_variant_ids[0]
        self.env["stock.quant"]._update_available_quantity(
            product, self.warehouse.lot_stock_id, 1, trace_id=self.lot
        )
        self.lot.invalidate_recordset(["location_id"])
        order = self.plan._get_open_order()
        sent = order._create_transfer(*order._resolve_warehouse_route())
        sent.move_ids.picked = True
        sent._action_done()

        wizard = (
            self.env["wizard.stock.picking.return"]
            .with_context(active_id=sent.id, active_model="stock.picking")
            .create({})
        )
        wizard.product_return_moves.quantity = 1
        returned = self.env["stock.picking"].browse(
            wizard.action_create_returns()["res_id"]
        )
        returned.move_ids.move_line_ids.write({"quantity": 1, "trace_id": self.lot.id})
        returned.with_user(self.warehouse_user).button_validate()
        self.assertEqual(returned.state, "done")
        self.assertEqual(order.state, "done")
        self.assertGreater(self.plan.date_next_scheduled, fields.Datetime.now())

    def test_a_warehouse_user_opens_the_order_its_transfer_moves(self):
        product = self.template.product_variant_ids[0]
        self.env["stock.quant"]._update_available_quantity(
            product, self.warehouse.lot_stock_id, 1, trace_id=self.lot
        )
        self.lot.invalidate_recordset(["location_id"])
        order = self.plan._get_open_order()
        picking = order._create_transfer(*order._resolve_warehouse_route())
        action = picking.with_user(self.warehouse_user).action_view_maintenance_order()
        opened = (
            self.env["maintenance.order"]
            .with_user(self.warehouse_user)
            .browse(action["res_id"])
        )
        self.assertEqual(opened.read(["name"])[0]["id"], order.id)
        with self.assertRaises(AccessError):
            opened.write({"name": "Renamed"})

    def test_a_technician_without_plan_rights_closes_a_distance_plan_order(self):
        self.plan.write({"distance_interval": 1000, "user_id": self.plain_user.id})
        self.env["resource.asset.log"].create(
            {
                "asset_id": self.lot.asset_id.id,
                "date": fields.Date.today(),
                "odometer": 5000,
                "source": "manual",
            }
        )
        order = self.plan._get_open_order()
        order.user_id = self.plain_user
        order.with_user(self.plain_user).action_done()
        self.assertEqual(self.plan.last_maintenance_odometer, 5000)
        self.assertTrue(self.plan._get_open_order())

    def test_an_asset_user_sees_no_order_without_an_asset(self):
        asset_user = self.env["res.users"].create(
            {
                "name": "Asset user",
                "login": "maint_access_asset",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("asset_ledger.group_asset_user").id,
                            self.env.ref(
                                "asset_ledger.group_enable_machinery_assets"
                            ).id,
                        ],
                    )
                ],
            }
        )
        loose = self.env["maintenance.order"].create({"name": "Loose order"})
        planned = self.plan._get_open_order()
        visible = (
            self.env["maintenance.order"]
            .with_user(asset_user)
            .search([("id", "in", (loose | planned).ids)])
        )
        self.assertEqual(visible, planned)
