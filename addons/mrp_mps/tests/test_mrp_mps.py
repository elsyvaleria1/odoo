from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command
from odoo.tests import Form, common
from odoo.tools.date_utils import start_of, subtract


class TestMpsMps(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.mps_dates_month = cls.env.company._get_date_range()
        cls.manufacture_route = cls.env.ref("mrp.route_warehouse0_manufacture")

        cls.table = cls.env["product.product"].create(
            {
                "name": "Table",
                "is_storable": True,
                "route_ids": [Command.set([cls.manufacture_route.id])],
            }
        )
        cls.drawer = cls.env["product.product"].create(
            {
                "name": "Drawer",
                "is_storable": True,
                "route_ids": [Command.set([cls.manufacture_route.id])],
            }
        )
        cls.table_leg = cls.env["product.product"].create(
            {
                "name": "Table Leg",
                "is_storable": True,
                "route_ids": [Command.set([cls.manufacture_route.id])],
            }
        )
        cls.screw = cls.env["product.product"].create(
            {
                "name": "Screw",
                "is_storable": True,
            }
        )
        cls.bolt = cls.env["product.product"].create(
            {
                "name": "Bolt",
                "is_storable": True,
            }
        )
        bom_form_table = Form(cls.env["mrp.bom"])
        bom_form_table.product_tmpl_id = cls.table.product_tmpl_id
        bom_form_table.product_qty = 1
        cls.bom_table = bom_form_table.save()

        with Form(cls.bom_table) as bom:
            with bom.bom_line_ids.new() as line:
                line.product_id = cls.drawer
                line.product_qty = 1
            with bom.bom_line_ids.new() as line:
                line.product_id = cls.table_leg
                line.product_qty = 2

        bom_form_drawer = Form(cls.env["mrp.bom"])
        bom_form_drawer.product_tmpl_id = cls.drawer.product_tmpl_id
        bom_form_drawer.product_qty = 1
        cls.bom_drawer = bom_form_drawer.save()

        with Form(cls.bom_drawer) as bom:
            with bom.bom_line_ids.new() as line:
                line.product_id = cls.table_leg
                line.product_qty = 2
            with bom.bom_line_ids.new() as line:
                line.product_id = cls.screw
                line.product_qty = 4

        bom_form_table_leg = Form(cls.env["mrp.bom"])
        bom_form_table_leg.product_tmpl_id = cls.table_leg.product_tmpl_id
        bom_form_table_leg.product_qty = 1
        cls.bom_table_leg = bom_form_table_leg.save()

        with Form(cls.bom_table_leg) as bom:
            with bom.bom_line_ids.new() as line:
                line.product_id = cls.bolt
                line.product_qty = 4
            with bom.bom_line_ids.new() as line:
                line.product_id = cls.screw
                line.product_qty = 4

        cls.wardrobe = cls.env["product.product"].create(
            {
                "name": "Wardrobe",
                "is_storable": True,
            }
        )

        bom_form_wardrobe = Form(cls.env["mrp.bom"])
        bom_form_wardrobe.product_tmpl_id = cls.wardrobe.product_tmpl_id
        bom_form_wardrobe.product_qty = 1
        cls.bom_wardrobe = bom_form_wardrobe.save()

        with Form(cls.bom_wardrobe) as bom:
            with bom.bom_line_ids.new() as line:
                line.product_id = cls.drawer
                line.product_qty = 3

        cls.chair = cls.env["product.product"].create(
            {
                "name": "Chair",
                "is_storable": True,
            }
        )

        bom_form_chair = Form(cls.env["mrp.bom"])
        bom_form_chair.product_tmpl_id = cls.chair.product_tmpl_id
        bom_form_chair.product_qty = 1
        cls.bom_chair = bom_form_chair.save()

        with Form(cls.bom_chair) as bom:
            with bom.bom_line_ids.new() as line:
                line.product_id = cls.table_leg
                line.product_qty = 4

        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.mps_table = cls.env["mrp.production.schedule"].create(
            {
                "product_id": cls.table.id,
                "warehouse_id": cls.warehouse.id,
                "bom_id": cls.bom_table.id,
            }
        )
        cls.mps_wardrobe = cls.env["mrp.production.schedule"].create(
            {
                "product_id": cls.wardrobe.id,
                "warehouse_id": cls.warehouse.id,
                "bom_id": cls.bom_wardrobe.id,
            }
        )
        cls.mps_chair = cls.env["mrp.production.schedule"].create(
            {
                "product_id": cls.chair.id,
                "warehouse_id": cls.warehouse.id,
                "bom_id": cls.bom_chair.id,
            }
        )
        cls.mps_drawer = cls.env["mrp.production.schedule"].create(
            {
                "product_id": cls.drawer.id,
                "warehouse_id": cls.warehouse.id,
                "bom_id": cls.bom_drawer.id,
            }
        )
        cls.mps_table_leg = cls.env["mrp.production.schedule"].create(
            {
                "product_id": cls.table_leg.id,
                "warehouse_id": cls.warehouse.id,
                "bom_id": cls.bom_table_leg.id,
            }
        )
        cls.mps_screw = cls.env["mrp.production.schedule"].search(
            [("product_id", "=", cls.screw.id)]
        )
        cls.mps_bolt = cls.env["mrp.production.schedule"].search(
            [("product_id", "=", cls.bolt.id)]
        )
        cls.mps = (
            cls.mps_table
            | cls.mps_wardrobe
            | cls.mps_chair
            | cls.mps_drawer
            | cls.mps_table_leg
            | cls.mps_screw
            | cls.mps_bolt
        )

    def _create_and_process_delivery_at_date(
        self, products_and_quantities, date=False, to_validate=True
    ):
        date = date or datetime.now()
        delivery_type = self.env.ref("stock.warehouse0").out_type_id
        with freeze_time(date):
            delivery = self.env["stock.picking"].create(
                {
                    "picking_type_id": delivery_type.id,
                    "location_id": delivery_type.default_location_src_id.id,
                    "location_dest_id": delivery_type.default_location_dest_id.id,
                    "move_ids": [
                        Command.create(
                            {
                                "location_id": delivery_type.default_location_src_id.id,
                                "location_dest_id": delivery_type.default_location_dest_id.id,
                                "product_id": product.id,
                                "quantity": qty,
                                "product_uom_qty": qty,
                            }
                        )
                        for (product, qty) in products_and_quantities
                    ],
                }
            )
            delivery.action_confirm()
            if to_validate:
                delivery.action_assign()
                delivery.button_validate()
            return delivery

    def test_basic_state(self):
        mps_state = self.mps.get_mps_view_state()
        self.assertTrue(len(mps_state["manufacturing_period"]), 12)

        production_schedule_ids = [
            s for s in mps_state["production_schedule_ids"] if s["id"] in self.mps.ids
        ]
        self.assertEqual(len(production_schedule_ids), 7)
        self.assertEqual(mps_state["company_id"], self.env.user.company_id.id)
        company_groups = mps_state["groups"][0]
        self.assertTrue(company_groups["mrp_mps_show_starting_inventory"])
        self.assertTrue(company_groups["mrp_mps_show_demand_forecast"])
        self.assertTrue(company_groups["mrp_mps_show_indirect_demand"])
        self.assertTrue(company_groups["mrp_mps_show_to_replenish"])
        self.assertTrue(company_groups["mrp_mps_show_safety_stock"])

        self.assertFalse(company_groups["mrp_mps_show_actual_demand"])
        self.assertFalse(company_groups["mrp_mps_show_actual_replenishment"])
        self.assertFalse(company_groups["mrp_mps_show_available_to_promise"])

        self.assertTrue(
            all(
                not forecast["starting_inventory_qty"]
                for forecast in production_schedule_ids[0]["forecast_ids"]
            )
        )
        self.assertTrue(
            all(
                not forecast["forecast_qty"]
                for forecast in production_schedule_ids[0]["forecast_ids"]
            )
        )
        self.assertTrue(
            all(
                not forecast["replenish_qty"]
                for forecast in production_schedule_ids[0]["forecast_ids"]
            )
        )
        self.assertTrue(
            all(
                not forecast["safety_stock_qty"]
                for forecast in production_schedule_ids[0]["forecast_ids"]
            )
        )
        self.assertTrue(
            all(
                not forecast["indirect_demand_qty"]
                for forecast in production_schedule_ids[0]["forecast_ids"]
            )
        )
        self.assertTrue(
            all(
                len(production_schedule_id["forecast_ids"]) == 12
                for production_schedule_id in production_schedule_ids
            )
        )

    def test_forecast_1(self):
        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_screw.id,
                "date": date.today(),
                "forecast_qty": 100,
            }
        )
        screw_mps_state = self.mps_screw.get_production_schedule_view_state()[0]
        forecast_at_first_period = screw_mps_state["forecast_ids"][0]
        self.assertEqual(forecast_at_first_period["forecast_qty"], 100)
        self.assertEqual(forecast_at_first_period["replenish_qty"], 100)
        self.assertEqual(forecast_at_first_period["safety_stock_qty"], 0)

        self.env["stock.quant"]._update_available_quantity(
            self.mps_screw.product_id, self.warehouse.lot_stock_id, 50
        )
        self.env.invalidate_all()
        screw_mps_state = self.mps_screw.get_production_schedule_view_state()[0]
        forecast_at_first_period = screw_mps_state["forecast_ids"][0]
        self.assertEqual(forecast_at_first_period["forecast_qty"], 100)
        self.assertEqual(forecast_at_first_period["replenish_qty"], 50)
        self.assertEqual(forecast_at_first_period["safety_stock_qty"], 0)

    def test_replenish(self):
        self.env.company.stock_config_id.horizon_days = 0
        self.env.user.tz = "UTC"
        forecast_screw = self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_screw.id,
                "date": self.mps_dates_month[0][0],
                "forecast_qty": 100,
            }
        )
        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_screw.id,
                "date": self.mps_dates_month[1][0],
                "forecast_qty": 100,
            }
        )

        partner = self.env["res.partner"].create({"name": "Jhon"})
        self.env["product.supplierinfo"].create(
            {
                "product_id": self.screw.id,
                "partner_id": partner.id,
                "price": 12.0,
                "delay": 0,
            }
        )
        self.mps_screw.action_replenish()
        purchase_order_line = self.env["purchase.order.line"].search(
            [("product_id", "=", self.screw.id)]
        )
        self.assertTrue(purchase_order_line)

        self.mps_screw.action_replenish(based_on_lead_time=True)
        purchase_order_line = self.env["purchase.order.line"].search(
            [("product_id", "=", self.screw.id)]
        )
        self.assertEqual(len(purchase_order_line), 1)

        self.mps_screw.action_replenish()
        purchase_order_lines = self.env["purchase.order.line"].search(
            [("product_id", "=", self.screw.id)]
        )
        self.assertEqual(len(purchase_order_lines), 2)
        self.assertEqual(len(purchase_order_lines.mapped("order_id")), 2)

        self.mps_screw.action_replenish()
        purchase_order_lines = self.env["purchase.order.line"].search(
            [("product_id", "=", self.screw.id)]
        )
        self.assertEqual(len(purchase_order_lines), 2)

        forecast_screw.forecast_qty = 150
        mps_screw = self.mps_screw.get_production_schedule_view_state()[0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        self.assertEqual(screw_forecast_1["state"], "to_relaunch")
        self.assertTrue(screw_forecast_1["to_replenish"])
        self.assertTrue(screw_forecast_1["forced_replenish"])

        self.mps_screw.action_replenish(based_on_lead_time=True)
        purchase_order_lines = self.env["purchase.order.line"].search(
            [("product_id", "=", self.screw.id)]
        )
        self.assertEqual(len(purchase_order_lines), 2)
        purchase_order_line = self.env["purchase.order.line"].search(
            [("product_id", "=", self.screw.id)], order="date_commitment", limit=1
        )
        self.assertEqual(purchase_order_line.product_qty, 150)

        forecast_screw.forecast_qty = 50
        mps_screw = self.mps_screw.get_production_schedule_view_state()[0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        self.assertEqual(screw_forecast_1["state"], "to_correct")
        self.assertFalse(screw_forecast_1["to_replenish"])
        self.assertFalse(screw_forecast_1["forced_replenish"])

    def test_lead_times(self):
        self.env.company.stock_config_id.horizon_days = 0
        self.env.company.manufacturing_period = "week"
        partner = self.env["res.partner"].create({"name": "Jhon"})
        seller = self.env["product.supplierinfo"].create(
            {
                "product_id": self.screw.id,
                "partner_id": partner.id,
                "price": 12.0,
                "delay": 7,
            }
        )

        mps_dates_week = self.env.company._get_date_range()
        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_screw.id,
                "date": mps_dates_week[0][0],
                "forecast_qty": 100,
            }
        )

        mps_screw = self.mps_screw.get_production_schedule_view_state()[0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        screw_forecast_2 = mps_screw["forecast_ids"][1]
        screw_forecast_3 = mps_screw["forecast_ids"][2]

        self.assertEqual(screw_forecast_1["state"], "to_launch")
        self.assertEqual(screw_forecast_2["state"], "launched")
        self.assertEqual(screw_forecast_3["state"], "to_launch")
        self.assertTrue(screw_forecast_1["to_replenish"])
        self.assertFalse(screw_forecast_2["to_replenish"])
        self.assertFalse(screw_forecast_3["to_replenish"])
        self.assertTrue(screw_forecast_1["forced_replenish"])
        self.assertFalse(screw_forecast_2["forced_replenish"])
        self.assertFalse(screw_forecast_3["forced_replenish"])

        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_screw.id,
                "date": mps_dates_week[1][0],
                "forecast_qty": 100,
            }
        )

        mps_screw = self.mps_screw.get_production_schedule_view_state()[0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        screw_forecast_2 = mps_screw["forecast_ids"][1]
        screw_forecast_3 = mps_screw["forecast_ids"][2]
        self.assertEqual(screw_forecast_1["state"], "to_launch")
        self.assertEqual(screw_forecast_2["state"], "to_launch")
        self.assertEqual(screw_forecast_3["state"], "to_launch")
        self.assertTrue(screw_forecast_1["to_replenish"])
        self.assertTrue(screw_forecast_2["to_replenish"])
        self.assertFalse(screw_forecast_3["to_replenish"])
        self.assertTrue(screw_forecast_1["forced_replenish"])
        self.assertFalse(screw_forecast_2["forced_replenish"])
        self.assertFalse(screw_forecast_3["forced_replenish"])
        seller.delay = 14
        mps_screw = self.mps_screw.get_production_schedule_view_state()[0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        screw_forecast_2 = mps_screw["forecast_ids"][1]
        screw_forecast_3 = mps_screw["forecast_ids"][2]
        self.assertEqual(screw_forecast_1["state"], "to_launch")
        self.assertEqual(screw_forecast_2["state"], "to_launch")
        self.assertEqual(screw_forecast_3["state"], "launched")
        self.assertTrue(screw_forecast_1["to_replenish"])
        self.assertTrue(screw_forecast_2["to_replenish"])
        self.assertFalse(screw_forecast_3["to_replenish"])
        self.assertTrue(screw_forecast_1["forced_replenish"])
        self.assertFalse(screw_forecast_2["forced_replenish"])
        self.assertFalse(screw_forecast_3["forced_replenish"])

        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_screw.id,
                "date": mps_dates_week[2][0],
                "forecast_qty": 100,
            }
        )
        mps_screw = self.mps_screw.get_production_schedule_view_state()[0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        screw_forecast_2 = mps_screw["forecast_ids"][1]
        screw_forecast_3 = mps_screw["forecast_ids"][2]
        self.assertEqual(screw_forecast_1["state"], "to_launch")
        self.assertEqual(screw_forecast_2["state"], "to_launch")
        self.assertEqual(screw_forecast_3["state"], "to_launch")
        self.assertTrue(screw_forecast_1["to_replenish"])
        self.assertTrue(screw_forecast_2["to_replenish"])
        self.assertTrue(screw_forecast_3["to_replenish"])
        self.assertTrue(screw_forecast_1["forced_replenish"])
        self.assertFalse(screw_forecast_2["forced_replenish"])
        self.assertFalse(screw_forecast_3["forced_replenish"])

        self.mps_screw.action_replenish(based_on_lead_time=True)
        purchase_order_line = self.env["purchase.order.line"].search(
            [("product_id", "=", self.screw.id)]
        )
        self.assertEqual(len(purchase_order_line.mapped("order_id")), 3)

        mps_screw = self.mps_screw.get_production_schedule_view_state()[0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        screw_forecast_2 = mps_screw["forecast_ids"][1]
        screw_forecast_3 = mps_screw["forecast_ids"][2]
        self.assertEqual(screw_forecast_1["state"], "launched")
        self.assertEqual(screw_forecast_2["state"], "launched")
        self.assertEqual(screw_forecast_3["state"], "launched")
        self.assertFalse(screw_forecast_1["to_replenish"])
        self.assertFalse(screw_forecast_2["to_replenish"])
        self.assertFalse(screw_forecast_3["to_replenish"])
        self.assertFalse(screw_forecast_1["forced_replenish"])
        self.assertFalse(screw_forecast_2["forced_replenish"])
        self.assertFalse(screw_forecast_3["forced_replenish"])

    def test_lead_times_2(self):
        self.env.company.stock_config_id.horizon_days = 0
        self.env.company.manufacturing_period = "month"
        self.table.write(
            {"route_ids": [(6, 0, [self.ref("mrp.route_warehouse0_manufacture")])]}
        )
        self.drawer.write(
            {"route_ids": [(6, 0, [self.ref("mrp.route_warehouse0_manufacture")])]}
        )
        self.table_leg.write(
            {"route_ids": [(6, 0, [self.ref("mrp.route_warehouse0_manufacture")])]}
        )
        self.bom_table.produce_delay = 10
        self.bom_drawer.produce_delay = 15
        self.bom_table_leg.produce_delay = 10

        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_table.id,
                "date": self.mps_dates_month[3][0],
                "forecast_qty": 1,
            }
        )
        drawer_forecasts = self.mps_drawer.get_production_schedule_view_state()[0][
            "forecast_ids"
        ]
        self.assertEqual(drawer_forecasts[2]["indirect_demand_qty"], 1)
        table_leg_forecasts = self.mps_table_leg.get_production_schedule_view_state()[
            0
        ]["forecast_ids"]
        self.assertEqual(table_leg_forecasts[2]["indirect_demand_qty"], 4)
        screw_forecasts = self.mps_screw.get_production_schedule_view_state()[0][
            "forecast_ids"
        ]
        self.assertEqual(screw_forecasts[2]["indirect_demand_qty"], 12)
        self.assertEqual(screw_forecasts[1]["indirect_demand_qty"], 8)
        bolt_forecasts = self.mps_bolt.get_production_schedule_view_state()[0][
            "forecast_ids"
        ]
        self.assertEqual(bolt_forecasts[2]["indirect_demand_qty"], 8)
        self.assertEqual(bolt_forecasts[1]["indirect_demand_qty"], 8)

    @freeze_time("2024-10-01")
    def test_lead_times_3(self):
        self.env.company.stock_config_id.horizon_days = 0
        self.env.company.manufacturing_period = "month"
        self.table.write(
            {"route_ids": [Command.set([self.ref("mrp.route_warehouse0_manufacture")])]}
        )
        self.bom_table.produce_delay = 1
        self.mps_table.set_forecast_qty(1, 10)
        self.mps_table.set_forecast_qty(2, 10)
        self.mps_table.set_forecast_qty(3, 10)
        self.mps_table.set_forecast_qty(4, 10)

        mps_table, mps_drawer = (
            self.mps_table | self.mps_drawer
        ).get_production_schedule_view_state(period_scale="year")
        self.assertListEqual(
            [f["forecast_qty"] for f in mps_table["forecast_ids"]], [20, 20, 0]
        )
        self.assertListEqual(
            [f["indirect_demand_qty"] for f in mps_drawer["forecast_ids"]], [30, 10, 0]
        )

    def test_indirect_demand(self):

        self.env.company.stock_config_id.horizon_days = 0
        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_table.id,
                "date": self.mps_dates_month[0][0],
                "forecast_qty": 2,
            }
        )

        mps_drawer = self.mps_drawer.get_production_schedule_view_state()[0]
        drawer_forecast_1 = mps_drawer["forecast_ids"][0]
        self.assertEqual(drawer_forecast_1["indirect_demand_qty"], 2)
        mps_screw = self.mps_screw.get_production_schedule_view_state()[0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        self.assertEqual(screw_forecast_1["indirect_demand_qty"], 40)

        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_wardrobe.id,
                "date": self.mps_dates_month[0][0],
                "forecast_qty": 3,
            }
        )

        mps_drawer, mps_screw = (
            self.mps_drawer | self.mps_screw
        ).get_production_schedule_view_state()
        drawer_forecast_1 = mps_drawer["forecast_ids"][0]
        self.assertEqual(drawer_forecast_1["indirect_demand_qty"], 11)
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        self.assertEqual(screw_forecast_1["indirect_demand_qty"], 148)

        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_table.id,
                "date": self.mps_dates_month[1][0],
                "forecast_qty": 2,
            }
        )
        mps_drawer, mps_screw = (
            self.mps_drawer | self.mps_screw
        ).get_production_schedule_view_state()
        drawer_forecast_1 = mps_drawer["forecast_ids"][0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        screw_forecast_2 = mps_screw["forecast_ids"][1]
        self.assertEqual(drawer_forecast_1["indirect_demand_qty"], 11)
        self.assertEqual(screw_forecast_1["indirect_demand_qty"], 148)
        self.assertEqual(screw_forecast_2["indirect_demand_qty"], 40)

        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_table_leg.id,
                "date": self.mps_dates_month[1][0],
                "forecast_qty": 4,
            }
        )
        mps_screw = self.mps_screw.get_production_schedule_view_state()[0]
        screw_forecast_2 = mps_screw["forecast_ids"][1]
        self.assertEqual(screw_forecast_2["indirect_demand_qty"], 56)

        self.mps_table_leg.set_replenish_qty(date_index=1, quantity=3)
        mps_screw = self.mps_screw.get_production_schedule_view_state()[0]
        screw_forecast_2 = mps_screw["forecast_ids"][1]
        screw_forecast_3 = mps_screw["forecast_ids"][2]
        self.assertEqual(screw_forecast_2["indirect_demand_qty"], 20)
        self.assertEqual(screw_forecast_3["indirect_demand_qty"], 36)

    def test_indirect_demand_kit(self):
        cabinet = self.env["product.product"].create(
            {
                "name": "Cabinet",
                "is_storable": True,
            }
        )
        wood_kit = self.env["product.product"].create(
            {
                "name": "Wood Kit",
                "is_storable": True,
            }
        )
        wood = self.env["product.product"].create(
            {
                "name": "Wood",
                "is_storable": True,
            }
        )

        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": cabinet.product_tmpl_id.id,
                "product_qty": 1,
                "bom_line_ids": [
                    Command.create({"product_id": wood_kit.id, "product_qty": 1}),
                ],
            }
        )

        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": wood_kit.product_tmpl_id.id,
                "product_qty": 1,
                "bom_line_ids": [
                    Command.create({"product_id": wood.id, "product_qty": 2}),
                ],
            }
        )

        mps_cabinet = self.env["mrp.production.schedule"].create(
            {
                "product_id": cabinet.id,
                "warehouse_id": self.warehouse.id,
            }
        )

        mps_wood = self.env["mrp.production.schedule"].create(
            {
                "product_id": wood.id,
                "warehouse_id": self.warehouse.id,
            }
        )

        self.mps |= mps_cabinet | mps_wood

        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": mps_cabinet.id,
                "date": self.mps_dates_month[0][0],
                "forecast_qty": 2,
            }
        )

        mps_wood = mps_wood.get_production_schedule_view_state()[0]
        wood_forecast_1 = mps_wood["forecast_ids"][0]
        self.assertEqual(wood_forecast_1["indirect_demand_qty"], 4)

    def test_delivery_quantity_kit(self):
        second_warehouse = self.env["stock.warehouse"].create(
            {
                "name": "Second Warehouse",
                "code": "WH2",
                "resupply_wh_ids": [Command.link(self.warehouse.id)],
            }
        )

        resupply_route = self.env["stock.route"].search(
            [
                ("supplier_wh_id", "=", self.warehouse.id),
                ("supplied_wh_id", "=", second_warehouse.id),
            ],
            limit=1,
        )
        self.drawer.route_ids = [Command.set(resupply_route.ids)]

        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": self.wardrobe.product_tmpl_id.id,
                "type": "phantom",
                "product_qty": 2,
                "bom_line_ids": [
                    Command.create({"product_id": self.drawer.id, "product_qty": 6}),
                ],
            }
        )

        mps_wardrobe = self.env["mrp.production.schedule"].create(
            {
                "product_id": self.wardrobe.id,
                "warehouse_id": second_warehouse.id,
                "route_id": resupply_route.id,
            }
        )

        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": mps_wardrobe.id,
                "date": self.mps_dates_month[0][0],
                "forecast_qty": 4,
            }
        )

        mps_wardrobe.action_replenish()
        self.assertEqual(
            self.env["stock.move"]
            .search([("product_id", "=", self.drawer.id)], limit=1)
            .product_qty,
            12,
        )

    def test_impacted_schedule(self):
        impacted_schedules = self.mps_screw.get_impacted_schedule()
        self.assertEqual(
            sorted(impacted_schedules),
            sorted((self.mps - (self.mps_screw | self.mps_bolt)).ids),
        )

        impacted_schedules = self.mps_drawer.get_impacted_schedule()
        self.assertEqual(
            sorted(impacted_schedules),
            sorted(
                (
                    self.mps_table
                    | self.mps_wardrobe
                    | self.mps_table_leg
                    | self.mps_screw
                    | self.mps_bolt
                ).ids
            ),
        )

    def test_3_steps(self):
        self.warehouse.manufacture_steps = "pbm_sam"
        self.table_leg.write(
            {"route_ids": [(6, 0, [self.ref("mrp.route_warehouse0_manufacture")])]}
        )

        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_table_leg.id,
                "date": date.today(),
                "forecast_qty": 25,
            }
        )

        self.mps_table_leg.action_replenish()
        mps_table_leg = self.mps_table_leg.get_production_schedule_view_state()[0]
        self.assertEqual(
            mps_table_leg["forecast_ids"][0]["forecast_qty"],
            25.0,
            "Wrong resulting value of to_supply",
        )
        self.assertEqual(
            mps_table_leg["forecast_ids"][0]["qty_incoming"],
            25.0,
            "Wrong resulting value of incoming quantity",
        )

    def test_interwh_delay(self):
        main_warehouse = self.warehouse
        second_warehouse = self.env["stock.warehouse"].create(
            {
                "name": "Second Warehouse",
                "code": "WH02",
            }
        )
        main_warehouse.write({"resupply_wh_ids": [(6, 0, second_warehouse.ids)]})

        interwh_route = self.env["stock.route"].search(
            [
                ("supplied_wh_id", "=", main_warehouse.id),
                ("supplier_wh_id", "=", second_warehouse.id),
            ]
        )
        interwh_route.rule_ids.delay = 1

        product = self.env["product.product"].create(
            {
                "name": "SuperProduct",
                "is_storable": True,
                "route_ids": [(6, 0, interwh_route.ids)],
            }
        )

        mps = self.env["mrp.production.schedule"].create(
            {
                "product_id": product.id,
                "warehouse_id": main_warehouse.id,
            }
        )
        interval_index = 3
        mps.set_replenish_qty(interval_index, 1)
        mps.action_replenish()

        state = mps.get_production_schedule_view_state()[0]
        for index, forecast in enumerate(state["forecast_ids"]):
            self.assertEqual(
                forecast["qty_incoming"],
                1 if index == interval_index else 0,
                "Incoming qty is incorrect for index %s" % index,
            )

    def test_outgoing_sm_and_lead_time_out_of_date_range(self):
        self.env.company.manufacturing_period = "day"
        self.env.company.manufacturing_period_to_display_day = 10

        customer_location = self.env.ref("stock.stock_location_customers")
        stock_location = self.warehouse.lot_stock_id

        delivery_rule = self.env["stock.rule"].search(
            [
                ("warehouse_id", "=", self.warehouse.id),
                ("location_src_id", "=", stock_location.id),
                ("location_dest_id", "=", customer_location.id),
                ("action", "=", "pull"),
            ],
            limit=1,
        )
        delivery_rule.delay = 15

        product = self.env["product.product"].create(
            {"name": "SuperProduct", "is_storable": True}
        )
        procurement = self.env["stock.rule"].Procurement(
            product,
            1,
            product.uom_id,
            customer_location,
            product.name,
            "/",
            self.env.company,
            {
                "warehouse_id": self.warehouse,
                "date_planned": date.today() + timedelta(days=16),
            },
        )
        self.env["stock.rule"].run([procurement])

        tomorrow = start_of(datetime.now() + timedelta(days=1), "day")
        move = self.env["stock.move"].search([("product_id", "=", product.id)], limit=1)
        self.assertEqual(move.date, tomorrow)

        mps = self.env["mrp.production.schedule"].create(
            {
                "product_id": product.id,
                "warehouse_id": self.warehouse.id,
            }
        )
        state = mps.get_production_schedule_view_state()[0]
        self.assertTrue(
            all(forecast["qty_outgoing"] == 0 for forecast in state["forecast_ids"])
        )

    def test_product_variants_in_mps(self):
        size_attribute = self.env["product.attribute"].create(
            {"name": "Size", "sequence": 4}
        )
        self.env["product.attribute.value"].create(
            [
                {
                    "name": name,
                    "attribute_id": size_attribute.id,
                    "sequence": 1,
                }
                for name in ("M", "L")
            ]
        )
        product, c1, c2 = self.env["product.product"].create(
            [
                {
                    "name": i,
                    "is_storable": True,
                }
                for i in range(3)
            ]
        )
        product_template = product.product_tmpl_id
        size_attribute_line = self.env["product.template.attribute.line"].create(
            [
                {
                    "product_tmpl_id": product_template.id,
                    "attribute_id": size_attribute.id,
                    "value_ids": [(6, 0, size_attribute.value_ids.ids)],
                }
            ]
        )
        self.assertEqual(product_template.product_variant_count, 2)
        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": product_template.id,
                "product_uom_id": product_template.uom_id.id,
                "product_qty": 1.0,
                "type": "normal",
                "bom_line_ids": [
                    Command.create(
                        {
                            "product_id": c1.id,
                            "product_qty": 1,
                            "bom_product_template_attribute_value_ids": [
                                (
                                    4,
                                    size_attribute_line.product_template_value_ids[
                                        0
                                    ].id,
                                )
                            ],
                        }
                    ),
                    Command.create(
                        {
                            "product_id": c2.id,
                            "product_qty": 1,
                            "bom_product_template_attribute_value_ids": [
                                (
                                    4,
                                    size_attribute_line.product_template_value_ids[
                                        1
                                    ].id,
                                )
                            ],
                        }
                    ),
                ],
            }
        )

        mps_p_m, mps_p_l, mps_c1, mps_c2 = self.env["mrp.production.schedule"].create(
            [
                {
                    "product_id": product,
                    "warehouse_id": self.warehouse.id,
                }
                for product in (
                    product_template.product_variant_ids[0]
                    | product_template.product_variant_ids[1]
                    | c1
                    | c2
                ).ids
            ]
        )

        mps_impacted = mps_p_m[0].get_impacted_schedule()
        self.assertEqual(len(mps_impacted), 1)
        self.assertEqual(mps_impacted[0], mps_c1.id)
        mps_impacted = mps_p_l[0].get_impacted_schedule()
        self.assertEqual(len(mps_impacted), 1)
        self.assertEqual(mps_impacted[0], mps_c2.id)

    def test_replenish_trigger(self):
        mps_components = (
            self.mps_drawer + self.mps_table_leg + self.mps_screw + self.mps_bolt
        )
        self.assertTrue(
            all(record.replenish_trigger == "manual" for record in mps_components)
        )

        partner = self.env["res.partner"].create({"name": "Bob Palindrome MacScam"})
        seller = self.env["product.supplierinfo"].create(
            {
                "product_id": self.screw.id,
                "partner_id": partner.id,
                "price": 2,
                "delay": 3,
            }
        )
        self.mps_screw.write(
            {"replenish_trigger": "automated", "supplier_id": seller.id}
        )

        self.env.company.manufacturing_period = "month"
        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": self.mps_table.id,
                "date": datetime.today(),
                "forecast_qty": 1,
            }
        )

        self.env["mrp.production.schedule"].action_cron_replenish()
        purchase_order_line = self.env["purchase.order.line"].search(
            [("product_id", "=", self.screw.id)]
        )
        self.assertTrue(purchase_order_line)
        self.assertEqual(
            purchase_order_line.date_commitment.date(), self.mps_dates_month[0][0]
        )
        self.assertEqual(
            purchase_order_line.date_order.date(),
            self.mps_dates_month[0][0] - timedelta(days=3),
        )
        self.assertEqual(purchase_order_line.product_qty, 20)
        self.assertEqual(purchase_order_line.price_subtotal, 40)

    def test_set_forecast_qty(self):
        self.env.company.manufacturing_period = "month"
        for delta in (3, 6, 12, 21):
            self.env["mrp.product.forecast"].create(
                {
                    "production_schedule_id": self.mps_table.id,
                    "date": self.mps_dates_month[1][0] + timedelta(days=delta),
                    "forecast_qty": delta,
                }
            )

        forecast_records = self.env["mrp.product.forecast"].search(
            [("production_schedule_id", "=", self.mps_table.id)]
        )
        self.assertEqual(len(forecast_records), 4)
        self.assertEqual(
            sum(forecast_records.mapped("forecast_qty")),
            42,
            "This is not the Answer to Life, the Universe, and Everything.",
        )

        self.mps_table.set_forecast_qty(1, 64)
        forecast_records = self.env["mrp.product.forecast"].search(
            [("production_schedule_id", "=", self.mps_table.id)]
        )
        self.assertEqual(len(forecast_records), 5)
        self.assertEqual(forecast_records.mapped("forecast_qty"), [22, 3, 6, 12, 21])
        self.assertEqual(forecast_records[0].date, self.mps_dates_month[1][0])

        self.mps_table.set_forecast_qty(1, 84)
        self.assertEqual(forecast_records.mapped("forecast_qty"), [42, 3, 6, 12, 21])

        self.mps_table.set_forecast_qty(1, 72)
        self.assertEqual(forecast_records.mapped("forecast_qty"), [42, 3, 6, 12, 9])

        self.mps_table.set_forecast_qty(1, 50)
        self.assertEqual(forecast_records.mapped("forecast_qty"), [42, 3, 5, 0, 0])

        self.mps_table.set_forecast_qty(1, 21)
        self.assertEqual(forecast_records.mapped("forecast_qty"), [21, 0, 0, 0, 0])

        self.mps_table.set_forecast_qty(1, -13)
        self.assertEqual(forecast_records.mapped("forecast_qty"), [-13, 0, 0, 0, 0])

    def test_mps_sequence(self):
        self.assertEqual(self.mps_table.mps_sequence, 10)
        self.assertEqual(self.mps_chair.mps_sequence, 10)
        self.assertEqual(self.mps_wardrobe.mps_sequence, 10)
        self.assertEqual(self.mps_table_leg.mps_sequence, 11)
        self.assertEqual(self.mps_drawer.mps_sequence, 11)
        self.assertEqual(self.mps_screw.mps_sequence, 12)
        self.assertEqual(self.mps_bolt.mps_sequence, 12)

    def test_mps_sequence_2(self):
        shelf = self.env["product.product"].create(
            {
                "name": "shelf",
                "is_storable": True,
            }
        )
        plank = self.env["product.product"].create(
            {
                "name": "plank",
                "is_storable": True,
            }
        )
        wood = self.env["product.product"].create(
            {
                "name": "wood",
                "is_storable": True,
            }
        )
        bom_shelf = self.env["mrp.bom"].create(
            {
                "product_id": shelf.id,
                "product_tmpl_id": shelf.product_tmpl_id.id,
                "product_uom_id": shelf.uom_id.id,
                "consumption": "flexible",
                "product_qty": 1.0,
                "type": "normal",
                "bom_line_ids": [
                    Command.create({"product_id": plank.id, "product_qty": 2}),
                    Command.create({"product_id": self.screw.id, "product_qty": 3}),
                ],
            }
        )
        bom_plank = self.env["mrp.bom"].create(
            {
                "product_id": plank.id,
                "product_tmpl_id": plank.product_tmpl_id.id,
                "product_uom_id": plank.uom_id.id,
                "consumption": "flexible",
                "product_qty": 1.0,
                "type": "normal",
                "bom_line_ids": [
                    Command.create({"product_id": wood.id, "product_qty": 2}),
                ],
            }
        )
        mps_wood = self.env["mrp.production.schedule"].create(
            {
                "product_id": wood.id,
                "warehouse_id": self.warehouse.id,
            }
        )
        self.assertEqual(mps_wood.mps_sequence, 10)
        mps_shelf = self.env["mrp.production.schedule"].create(
            {
                "product_id": shelf.id,
                "warehouse_id": self.warehouse.id,
                "bom_id": bom_shelf.id,
            }
        )
        self.assertEqual(mps_shelf.mps_sequence, 10)
        self.assertEqual(self.mps_screw.mps_sequence, 11)
        self.assertEqual(mps_wood.mps_sequence, 12)

        mps_plank = self.env["mrp.production.schedule"].create(
            {
                "product_id": plank.id,
                "warehouse_id": self.warehouse.id,
                "bom_id": bom_plank.id,
            }
        )
        self.assertEqual(mps_plank.mps_sequence, 11)
        self.assertEqual(mps_wood.mps_sequence, 12)

    def test_is_indirect(self):
        mps_components = (
            self.mps_drawer + self.mps_table_leg + self.mps_screw + self.mps_bolt
        )
        self.assertTrue(all(record.is_indirect for record in mps_components))

    def test_no_route_product_in_mps(self):
        self.mps_table.unlink()
        self.table.route_ids = [Command.clear()]
        self.assertEqual(len(self.table.route_ids), 0)

        mps_table_2 = self.env["mrp.production.schedule"].create(
            {
                "product_id": self.table.id,
                "warehouse_id": self.warehouse.id,
                "bom_id": self.bom_table.id,
            }
        )
        self.assertFalse(mps_table_2.route_id)

    @freeze_time("2024-01-01")
    def test_periods_display(self):
        self.env.company.manufacturing_period_to_display_year = 5
        self.env.company.manufacturing_period_to_display_month = 15
        self.env.company.manufacturing_period_to_display_week = 7
        self.env.company.manufacturing_period_to_display_day = 21

        mps_state_default = self.mps.get_mps_view_state()
        self.assertEqual(mps_state_default["manufacturing_period"], "month")
        self.assertEqual(
            len(mps_state_default["dates"]),
            self.env.company.manufacturing_period_to_display_month,
        )
        self.assertListEqual(
            mps_state_default["dates"][9:],
            ["Oct 2024", "Nov 2024", "Dec 2024", "Jan 2025", "Feb 2025", "Mar 2025"],
        )

        mps_state_year = self.mps.get_mps_view_state(period_scale="year")
        self.assertEqual(mps_state_year["manufacturing_period"], "year")
        self.assertEqual(
            len(mps_state_year["dates"]),
            self.env.company.manufacturing_period_to_display_year,
        )
        self.assertListEqual(
            mps_state_year["dates"], ["2024", "2025", "2026", "2027", "2028"]
        )

        mps_state_week = self.mps.get_mps_view_state(period_scale="week")
        self.assertEqual(
            len(mps_state_week["dates"]),
            self.env.company.manufacturing_period_to_display_week,
        )
        self.assertEqual(
            mps_state_week["dates"][2:5],
            ["Week 3 (15-21/Jan)", "Week 4 (22-28/Jan)", "Week 5 (29-4/Feb)"],
        )

        mps_state_day = self.mps.get_mps_view_state(period_scale="day")
        self.assertEqual(
            len(mps_state_day["dates"]),
            self.env.company.manufacturing_period_to_display_day,
        )
        self.assertEqual(
            mps_state_day["dates"][7:12],
            ["Jan 8", "Jan 9", "Jan 10", "Jan 11", "Jan 12"],
        )

    def test_outgoing_move_with_different_uom(self):
        product_a = self.env["product.product"].create(
            {
                "name": "product a test",
                "is_storable": True,
            }
        )
        mps = self.env["mrp.production.schedule"].create(
            {
                "product_id": product_a.id,
                "warehouse_id": self.warehouse.id,
            }
        )
        outgoing_move = self.env["stock.move"].create(
            {
                "product_id": product_a.id,
                "product_uom_qty": 1,
                "product_uom_id": self.env.ref("base.product_uom_dozen").id,
                "location_id": self.warehouse.lot_stock_id.id,
                "location_dest_id": self.env.ref("stock.stock_location_customers").id,
            }
        )
        incoming_move = self.env["stock.move"].create(
            {
                "product_id": product_a.id,
                "product_uom_qty": 1,
                "product_uom_id": self.env.ref("base.product_uom_dozen").id,
                "location_id": self.env.ref("stock.stock_location_customers").id,
                "location_dest_id": self.warehouse.lot_stock_id.id,
            }
        )
        (outgoing_move | incoming_move)._action_confirm()
        state = mps.get_production_schedule_view_state()[0]
        qty_outgoing = state["forecast_ids"][0]["qty_outgoing"]
        qty_incoming = state["forecast_ids"][0]["qty_incoming"]
        self.assertEqual(qty_outgoing, 12, "outgoing qty is incorrect")
        self.assertEqual(qty_incoming, 12, "incoming qty is incorrect")

    def test_forecast_target_qty(self):
        self.env.company.stock_config_id.horizon_days = 0
        self.mps_table.forecast_target_qty = 3
        mps_table, mps_table_leg, mps_screw = (
            self.mps_table | self.mps_table_leg | self.mps_screw
        ).get_production_schedule_view_state()
        table_forecast_10 = mps_table["forecast_ids"][9]
        leg_forecast_1 = mps_table_leg["forecast_ids"][0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        self.assertEqual(leg_forecast_1["replenish_qty"], 12)
        self.assertEqual(screw_forecast_1["replenish_qty"], 60)
        self.assertEqual(table_forecast_10["starting_inventory_qty"], 3)

        self.mps_table.set_replenish_qty(date_index=0, quantity=1)
        mps_table_leg, mps_screw = (
            self.mps_table_leg | self.mps_screw
        ).get_production_schedule_view_state()
        leg_forecast_1 = mps_table_leg["forecast_ids"][0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        leg_forecast_2 = mps_table_leg["forecast_ids"][1]
        screw_forecast_2 = mps_screw["forecast_ids"][1]
        self.assertEqual(leg_forecast_1["replenish_qty"], 4)
        self.assertEqual(screw_forecast_1["replenish_qty"], 20)
        self.assertEqual(leg_forecast_2["replenish_qty"], 8)
        self.assertEqual(screw_forecast_2["replenish_qty"], 40)

        self.mps_table_leg.set_forecast_qty(date_index=0, quantity=1)
        mps_bolt, mps_screw = (
            self.mps_bolt | self.mps_screw
        ).get_production_schedule_view_state()
        bolt_forecast_1 = mps_bolt["forecast_ids"][0]
        bolt_forecast_2 = mps_bolt["forecast_ids"][1]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        self.assertEqual(bolt_forecast_1["replenish_qty"], 20)
        self.assertEqual(bolt_forecast_2["replenish_qty"], 32)
        self.assertEqual(screw_forecast_1["replenish_qty"], 24)

        self.mps_table_leg.set_replenish_qty(date_index=0, quantity=6)
        mps_table_leg, mps_bolt = (
            self.mps_table_leg | self.mps_bolt
        ).get_production_schedule_view_state()
        leg_forecast_2 = mps_table_leg["forecast_ids"][1]
        bolt_forecast_2 = mps_bolt["forecast_ids"][1]
        self.assertEqual(leg_forecast_2["replenish_qty"], 7)
        self.assertEqual(bolt_forecast_2["replenish_qty"], 28)

        self.mps_drawer.forecast_target_qty = 5
        mps_drawer, mps_table_leg, mps_screw = (
            self.mps_drawer | self.mps_table_leg | self.mps_screw
        ).get_production_schedule_view_state()
        drawer_forecast_1 = mps_drawer["forecast_ids"][0]
        drawer_forecast_9 = mps_drawer["forecast_ids"][8]
        leg_forecast_2 = mps_table_leg["forecast_ids"][1]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        screw_forecast_2 = mps_screw["forecast_ids"][1]
        self.assertEqual(drawer_forecast_1["replenish_qty"], 6)
        self.assertEqual(drawer_forecast_9["starting_inventory_qty"], 5)
        self.assertEqual(leg_forecast_2["replenish_qty"], 17)
        self.assertEqual(screw_forecast_1["replenish_qty"], 48)
        self.assertEqual(screw_forecast_2["replenish_qty"], 76)

    def test_min_to_replenish_qty(self):
        self.mps_table_leg.write({"min_to_replenish_qty": 5})

        self.mps_table.set_forecast_qty(date_index=0, quantity=1)
        mps_table_leg, mps_screw = (
            self.mps_table_leg | self.mps_screw
        ).get_production_schedule_view_state()
        leg_forecast_1 = mps_table_leg["forecast_ids"][0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        self.assertEqual(leg_forecast_1["indirect_demand_qty"], 4)
        self.assertEqual(leg_forecast_1["replenish_qty"], 5)
        self.assertEqual(screw_forecast_1["replenish_qty"], 24)

        self.mps_table.set_forecast_qty(date_index=0, quantity=2)
        mps_table_leg, mps_screw = (
            self.mps_table_leg | self.mps_screw
        ).get_production_schedule_view_state()
        leg_forecast_1 = mps_table_leg["forecast_ids"][0]
        screw_forecast_1 = mps_screw["forecast_ids"][0]
        self.assertEqual(leg_forecast_1["indirect_demand_qty"], 8)
        self.assertEqual(leg_forecast_1["replenish_qty"], 8)
        self.assertEqual(screw_forecast_1["replenish_qty"], 40)

    @freeze_time("2025-01-01")
    def test_starting_inventory_qty(self):
        self.env.company.stock_config_id.horizon_days = 0
        self.env["stock.quant"].create(
            {
                "product_id": self.table.id,
                "inventory_quantity": 5,
                "location_id": self.warehouse.lot_stock_id.id,
            }
        ).action_apply_inventory()

        self.mps_table.set_forecast_qty(2, 3)
        mps_table = self.mps_table.get_production_schedule_view_state()[0]
        table_forecast_1 = mps_table["forecast_ids"][0]
        table_forecast_3 = mps_table["forecast_ids"][2]
        table_forecast_5 = mps_table["forecast_ids"][4]
        self.assertEqual(table_forecast_1["starting_inventory_qty"], 5)
        self.assertEqual(table_forecast_3["starting_inventory_qty"], 5)
        self.assertEqual(table_forecast_3["replenish_qty"], 0)
        self.assertEqual(table_forecast_3["safety_stock_qty"], 2)
        self.assertEqual(table_forecast_5["starting_inventory_qty"], 2)

        self.mps_table.set_forecast_qty(1, 4)
        mps_table, mps_table_leg, mps_screw = (
            self.mps_table | self.mps_table_leg | self.mps_screw
        ).get_production_schedule_view_state()
        table_forecast_2 = mps_table["forecast_ids"][1]
        table_forecast_3 = mps_table["forecast_ids"][2]
        table_forecast_7 = mps_table["forecast_ids"][6]
        leg_forecast_3 = mps_table_leg["forecast_ids"][2]
        screw_forecast_3 = mps_screw["forecast_ids"][2]
        self.assertEqual(table_forecast_2["starting_inventory_qty"], 5)
        self.assertEqual(table_forecast_2["replenish_qty"], 0)
        self.assertEqual(table_forecast_2["safety_stock_qty"], 1)
        self.assertEqual(table_forecast_3["starting_inventory_qty"], 1)
        self.assertEqual(table_forecast_3["replenish_qty"], 2)
        self.assertEqual(table_forecast_7["starting_inventory_qty"], 0)
        self.assertEqual(leg_forecast_3["replenish_qty"], 8)
        self.assertEqual(screw_forecast_3["replenish_qty"], 40)

        self.bom_table.produce_delay = 1
        self.table.write(
            {"route_ids": [Command.set([self.ref("mrp.route_warehouse0_manufacture")])]}
        )
        mps_table, mps_table_leg, mps_screw = (
            self.mps_table | self.mps_table_leg | self.mps_screw
        ).get_production_schedule_view_state()
        table_forecast_7 = mps_table["forecast_ids"][6]
        leg_forecast_2 = mps_table_leg["forecast_ids"][1]
        screw_forecast_2 = mps_screw["forecast_ids"][1]
        self.assertEqual(table_forecast_7["starting_inventory_qty"], 0)
        self.assertEqual(leg_forecast_2["replenish_qty"], 8)
        self.assertEqual(screw_forecast_2["replenish_qty"], 40)

        mps_table_leg, mps_screw = (
            self.mps_table_leg | self.mps_screw
        ).get_production_schedule_view_state(period_scale="week")
        leg_forecast_8 = mps_table_leg["forecast_ids"][7]
        leg_forecast_9 = mps_table_leg["forecast_ids"][8]
        screw_forecast_9 = mps_screw["forecast_ids"][8]
        self.assertEqual(leg_forecast_8["indirect_demand_qty"], 0)
        self.assertEqual(leg_forecast_9["indirect_demand_qty"], 8)
        self.assertEqual(screw_forecast_9["indirect_demand_qty"], 40)

        self.mps_table.set_forecast_qty(
            8, 0, period_scale="week"
        )
        self.mps_table.set_forecast_qty(
            9, 3, period_scale="week"
        )
        mps_table_leg, mps_screw = (
            self.mps_table_leg | self.mps_screw
        ).get_production_schedule_view_state(period_scale="week")
        leg_forecast_9 = mps_table_leg["forecast_ids"][8]
        screw_forecast_9 = mps_screw["forecast_ids"][8]
        self.assertEqual(leg_forecast_9["indirect_demand_qty"], 8)
        self.assertEqual(screw_forecast_9["indirect_demand_qty"], 40)

        mps_table_leg, mps_screw = (
            self.mps_table_leg | self.mps_screw
        ).get_production_schedule_view_state(period_scale="month")
        leg_forecast_2 = mps_table_leg["forecast_ids"][1]
        leg_forecast_3 = mps_table_leg["forecast_ids"][2]
        screw_forecast_3 = mps_screw["forecast_ids"][2]
        self.assertEqual(leg_forecast_2["indirect_demand_qty"], 0)
        self.assertEqual(leg_forecast_3["indirect_demand_qty"], 8)
        self.assertEqual(screw_forecast_3["indirect_demand_qty"], 40)

    def test_actual_replenishment_wizard(self):
        partner = self.env["res.partner"].create({"name": "Bob Palindrome MacScam"})
        self.env["product.supplierinfo"].create(
            {
                "product_id": self.screw.id,
                "partner_id": partner.id,
                "price": 12.0,
                "delay": 0,
            }
        )
        self.table.route_ids = [
            Command.set([self.ref("mrp.route_warehouse0_manufacture")])
        ]

        self.mps_table.set_forecast_qty(0, 1)
        (self.mps_table | self.mps_screw).action_replenish()
        purchase_order_line = self.env["purchase.order.line"].search(
            [("product_id", "=", self.screw.id)]
        )
        purchase_order_line.write(
            {
                "product_uom_id": self.env.ref("base.product_uom_dozen").id,
                "product_qty": 2,
            }
        )
        purchase_order_line.order_id.action_confirm()
        self.mps_screw.set_forecast_qty(0, 7)
        self.mps_screw.action_replenish()

        table_action = self.mps_table.action_view_actual_replenishment_details(
            "Wizard table testing",
            self.mps_dates_month[0][0],
            self.mps_dates_month[0][1],
        )
        table_wizard = Form.from_action(self.env, table_action)
        self.assertEqual(table_wizard.manufacture_qty, 1)
        screw_action = self.mps_screw.action_view_actual_replenishment_details(
            "Wizard screw testing",
            self.mps_dates_month[0][0],
            self.mps_dates_month[0][1],
        )
        screw_wizard = Form.from_action(self.env, screw_action)
        self.assertEqual(screw_wizard.moves_qty, 24)
        self.assertEqual(screw_wizard.rfq_qty, 3)
        purchase_order_line_2 = self.env["purchase.order.line"].search(
            [("product_id", "=", self.screw.id), ("id", "!=", purchase_order_line.id)]
        )
        purchase_order_line_2.write(
            {
                "product_uom_id": self.env.ref("base.product_uom_dozen").id,
                "product_qty": 1,
            }
        )
        screw_wizard_2 = Form.from_action(self.env, screw_action)
        self.assertEqual(screw_wizard_2.moves_qty, 24)
        self.assertEqual(screw_wizard_2.rfq_qty, 12)

    def test_actual_indirect_demand(self):
        today = datetime.now().date()

        self._create_and_process_delivery_at_date([(self.drawer, 10)], today)

        production = self.env["mrp.production"].create(
            {
                "product_id": self.table.id,
                "product_qty": 5,
                "product_uom_id": self.table.uom_id.id,
                "bom_id": self.bom_table.id,
                "location_src_id": self.warehouse.lot_stock_id.id,
                "location_dest_id": self.warehouse.lot_stock_id.id,
                "origin": "Test MPS",
            }
        )
        production.action_confirm()
        production.button_mark_done()

        mps_drawer = self.mps_drawer.get_production_schedule_view_state()[0]
        drawer_forecast = mps_drawer["forecast_ids"][0]
        self.assertEqual(drawer_forecast["qty_outgoing"], 10)
        self.assertEqual(drawer_forecast["indirect_outgoing_qty"], 5)

    def test_early_replenishment_calculation(self):
        partner = self.env["res.partner"].create({"name": "Al-Khwarizmi"})
        self.env["product.supplierinfo"].create(
            {
                "product_id": self.screw.id,
                "partner_id": partner.id,
                "price": 12.0,
                "delay": 0,
            }
        )
        self.table.route_ids = [
            Command.set([self.ref("mrp.route_warehouse0_manufacture")])
        ]

        self.mps_table.set_forecast_qty(0, 1)
        (self.mps_table | self.mps_screw).action_replenish()
        purchase_order_line = self.env["purchase.order.line"].search(
            [("product_id", "=", self.screw.id)]
        )
        purchase_order_line.write(
            {
                "product_uom_id": self.env.ref("base.product_uom_dozen").id,
                "product_qty": 2,
            }
        )
        purchase_order_line.order_id.action_confirm()
        self.mps_screw.set_forecast_qty(1, 2)
        self.mps_screw.set_forecast_qty(2, 5)

        mps_screw = self.mps_screw.get_production_schedule_view_state()[0]
        screw_forecast_1 = mps_screw["forecast_ids"][1]
        self.assertEqual(screw_forecast_1["replenish_qty"], 0)
        screw_forecast_2 = mps_screw["forecast_ids"][2]
        self.assertEqual(screw_forecast_2["replenish_qty"], 3)

    def test_actual_demand_multisteps(self):
        self.env["stock.quant"]._update_available_quantity(
            self.table, self.warehouse.lot_stock_id, 5
        )
        self.warehouse.delivery_steps = "pick_pack_ship"
        reference = self.env["stock.reference"].create(
            {"name": "Test-MPS-actual-demand-multisteps"}
        )
        self.env["stock.rule"].run(
            [
                self.env["stock.rule"].Procurement(
                    self.table,
                    5.0,
                    self.table.uom_id,
                    self.env.ref("stock.stock_location_customers"),
                    reference.name,
                    reference.name,
                    self.warehouse.company_id,
                    {
                        "warehouse_id": self.warehouse,
                        "reference_ids": reference,
                    },
                ),
            ]
        )

        pick_picking = reference.picking_ids
        mps_table = self.mps_table.get_production_schedule_view_state()[0]
        self.assertEqual(
            mps_table["forecast_ids"][0]["qty_outgoing"],
            5,
            "actual demand qty is incorrect",
        )
        domain_moves = self.mps_table._get_domain_moves(
            self.mps_dates_month[0][0], self.mps_dates_month[0][1], "outgoing"
        )
        mps_picking_1 = self.mps_table._get_moves_and_date(domain_moves)[0][
            0
        ].picking_id
        self.assertEqual(mps_picking_1, pick_picking, "It should be the pick_picking")

        pick_picking.button_validate()
        pack_picking = pick_picking.move_ids.move_dest_ids.picking_id
        mps_table = self.mps_table.get_production_schedule_view_state()[0]
        mps_picking_2 = self.mps_table._get_moves_and_date(domain_moves)[0][
            0
        ].picking_id
        self.assertEqual(
            mps_table["forecast_ids"][0]["qty_outgoing"],
            5,
            "actual demand qty is incorrect",
        )
        self.assertEqual(mps_picking_2, pack_picking, "It should be the pack_picking")

        pack_picking.button_validate()
        ship_picking = pack_picking.move_ids.move_dest_ids.picking_id
        mps_table = self.mps_table.get_production_schedule_view_state()[0]
        mps_picking_3 = self.mps_table._get_moves_and_date(domain_moves)[0][
            0
        ].picking_id
        self.assertEqual(
            mps_table["forecast_ids"][0]["qty_outgoing"],
            5,
            "actual demand qty is incorrect",
        )
        self.assertEqual(mps_picking_3, ship_picking, "It should be the ship_picking")

    def test_actual_demand_multisteps_2(self):
        second_warehouse = self.env["stock.warehouse"].create(
            {
                "name": "Cainhurst Castle",
                "code": "CC",
                "resupply_wh_ids": [Command.link(self.warehouse.id)],
            }
        )
        resupply_route = self.env["stock.route"].search(
            [
                ("supplier_wh_id", "=", self.warehouse.id),
                ("supplied_wh_id", "=", second_warehouse.id),
            ]
        )
        self.table.route_ids = [Command.set([resupply_route.id])]
        self.env["stock.quant"]._update_available_quantity(
            self.table, self.warehouse.lot_stock_id, 5
        )
        self.warehouse.delivery_steps = "pick_pack_ship"
        reference = self.env["stock.reference"].create(
            {"name": "Test-MPS-actual-demand-multisteps-interwarehouse"}
        )
        self.env["stock.rule"].run(
            [
                self.env["stock.rule"].Procurement(
                    self.table,
                    5.0,
                    self.table.uom_id,
                    second_warehouse.lot_stock_id,
                    reference.name,
                    reference.name,
                    second_warehouse.company_id,
                    {
                        "warehouse_id": second_warehouse,
                        "reference_ids": reference,
                    },
                ),
            ]
        )

        wh_transit_picking = reference.move_ids.filtered(
            lambda m: m.location_dest_id.usage == "transit"
        ).picking_id
        mps_table_wh0 = self.mps_table.get_production_schedule_view_state()[0]
        self.assertEqual(
            mps_table_wh0["forecast_ids"][0]["qty_outgoing"],
            5,
            "actual demand qty is incorrect",
        )
        domain_moves = self.mps_table._get_domain_moves(
            self.mps_dates_month[0][0], self.mps_dates_month[0][1], "outgoing"
        )
        mps_picking_wh_out = self.mps_table._get_moves_and_date(domain_moves)[0][
            0
        ].picking_id
        self.assertEqual(
            mps_picking_wh_out,
            wh_transit_picking,
            "It should be the transit picking for WH",
        )

        mps_record_table_cc = self.env["mrp.production.schedule"].create(
            {
                "product_id": self.table.id,
                "warehouse_id": second_warehouse.id,
                "bom_id": self.bom_table.id,
            }
        )
        cc_transit_picking = reference.move_ids.filtered(
            lambda m: m.location_id.usage == "transit"
        ).picking_id
        mps_table_cc0 = mps_record_table_cc.get_production_schedule_view_state()[0]
        self.assertEqual(
            mps_table_cc0["forecast_ids"][0]["qty_incoming"],
            5,
            "actual replenishment qty is incorrect",
        )
        domain_moves = mps_record_table_cc._get_domain_moves(
            self.mps_dates_month[0][0], self.mps_dates_month[0][1], "incoming"
        )
        mps_picking_cc_in = mps_record_table_cc._get_moves_and_date(domain_moves)[0][
            0
        ].picking_id
        self.assertEqual(
            mps_picking_cc_in,
            cc_transit_picking,
            "It should be the transit picking for CC",
        )

    def test_isolated_access(self):
        dummy = self.env["res.users"].create(
            {
                "name": "mps user",
                "login": "mps",
                "email": "test@test.test",
                "group_ids": [Command.set((self.env.ref("mrp.group_mrp_manager").id,))],
            }
        )
        for fname in self.env.company._fields:
            if self.env.company._is_field_mps_display_group(fname):
                self.env.company.with_user(dummy).write(
                    {fname: not self.env.company[fname]}
                )
        self.assertTrue(True)

    def test_mps_replenish_correct_bom(self):
        manufacture_route = self.env.ref("mrp.route_warehouse0_manufacture").id
        product = self.env["product.product"].create(
            {
                "name": "MPS Test Product",
                "is_storable": True,
                "route_ids": [Command.set([manufacture_route])],
            }
        )

        self.env["mrp.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "product_qty": 1,
                "bom_line_ids": [
                    Command.create({"product_id": self.screw.id, "product_qty": 2}),
                ],
            }
        )

        bom2 = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "product_qty": 1,
                "bom_line_ids": [
                    Command.create({"product_id": self.bolt.id, "product_qty": 4}),
                ],
            }
        )

        mps = self.env["mrp.production.schedule"].create(
            {
                "product_id": product.id,
                "warehouse_id": self.warehouse.id,
                "bom_id": bom2.id,
                "route_id": manufacture_route,
            }
        )
        self.env["mrp.product.forecast"].create(
            {
                "production_schedule_id": mps.id,
                "date": self.mps_dates_month[0][0],
                "forecast_qty": 100,
            }
        )
        mps.action_replenish()

        production = self.env["mrp.production"].search(
            [("product_id", "=", product.id)], limit=1
        )
        self.assertEqual(
            production.bom_id, bom2, "MO was created with an incorrect BOM"
        )

    @freeze_time("2024-02-14")
    def test_suggestion_for_years_with_period(self):

        today = datetime.now().date()

        date = today - relativedelta(years=1)
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        date = today - relativedelta(months=10)
        self._create_and_process_delivery_at_date([(self.table, 5)], date)

        date = today - relativedelta(years=2)
        self._create_and_process_delivery_at_date([(self.table, 4)], date)

        date = today
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        self._create_and_process_delivery_at_date(
            [(self.table, 10)], date, to_validate=False
        )

        self.env.company.manufacturing_period_to_display_year = 5
        table_suggestion_wizard = self.env[
            "wizard.mrp.production.schedule.update.forecast"
        ].create({"mrp_mps_id": self.mps_table.id, "period": 1})
        table_suggestion_wizard.with_context(
            {"period_scale": "year"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="year"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_year):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 15)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.period = 2
        table_suggestion_wizard.with_context(
            {"period_scale": "year"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="year"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_year):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 15)
            elif i == 1:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

    @freeze_time("2024-02-14")
    def test_suggestion_for_months_with_period(self):

        today = datetime.now().date()

        date = today - relativedelta(years=1)
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        date = today - relativedelta(months=10)
        self._create_and_process_delivery_at_date([(self.table, 5)], date)

        date = today - relativedelta(years=2)
        self._create_and_process_delivery_at_date([(self.table, 4)], date)

        date = today
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        self._create_and_process_delivery_at_date(
            [(self.table, 10)], date, to_validate=False
        )

        self.env.company.manufacturing_period_to_display_month = 25
        table_suggestion_wizard = self.env[
            "wizard.mrp.production.schedule.update.forecast"
        ].create({"mrp_mps_id": self.mps_table.id, "period": 1})
        table_suggestion_wizard.with_context(
            {"period_scale": "month"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="month"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_month):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.period = 3
        table_suggestion_wizard.with_context(
            {"period_scale": "month"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="month"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_month):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            elif i == 2:
                self.assertEqual(table_forecast["forecast_qty"], 5)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

    @freeze_time("2024-02-14")
    def test_suggestion_for_weeks_with_period(self):

        today = datetime.now().date()
        based_on_year = today.year - 1

        date = start_of(subtract(today, years=today.year - based_on_year), "week")
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        date = start_of(subtract(today, weeks=50), "week")
        self._create_and_process_delivery_at_date([(self.table, 5)], date)

        date = start_of(
            subtract(today, years=today.year - based_on_year, weeks=2), "week"
        )
        self._create_and_process_delivery_at_date([(self.table, 5)], date)

        date = start_of(today, "week")
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        self._create_and_process_delivery_at_date(
            [(self.table, 10)], date, to_validate=False
        )

        self.env.company.manufacturing_period_to_display_week = 105
        table_suggestion_wizard = self.env[
            "wizard.mrp.production.schedule.update.forecast"
        ].create({"mrp_mps_id": self.mps_table.id, "period": 1})
        table_suggestion_wizard.with_context(
            {"period_scale": "week"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="week"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_week):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.period = 3
        table_suggestion_wizard.with_context(
            {"period_scale": "week"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="week"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_week):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            elif i == 2:
                self.assertEqual(table_forecast["forecast_qty"], 5)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

    @freeze_time("2024-02-26")
    def test_suggestion_for_days_with_period(self):

        today = datetime.now().date()

        date = today + relativedelta(years=-1)
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        date = today - relativedelta(days=363)
        self._create_and_process_delivery_at_date([(self.table, 5)], date)

        date = today - relativedelta(years=2)
        self._create_and_process_delivery_at_date([(self.table, 4)], date)

        date = today
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        self._create_and_process_delivery_at_date(
            [(self.table, 10)], date, to_validate=False
        )

        self.env.company.manufacturing_period_to_display_day = 365
        table_suggestion_wizard = self.env[
            "wizard.mrp.production.schedule.update.forecast"
        ].create({"mrp_mps_id": self.mps_table.id, "period": 1})
        table_suggestion_wizard.with_context(
            {"period_scale": "day"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="day"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_day):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.period = 3
        table_suggestion_wizard.with_context(
            {"period_scale": "day"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="day"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_day):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            elif i == 2:
                self.assertEqual(table_forecast["forecast_qty"], 5)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

    @freeze_time("2024-02-14")
    def test_suggestion_for_years_with_no_period(self):

        today = datetime.now().date()
        self.table.uom_id.rounding = 1.0

        date = today - relativedelta(years=1)
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        date = today - relativedelta(months=10)
        self._create_and_process_delivery_at_date([(self.table, 5)], date)

        date = today - relativedelta(days=20)
        self._create_and_process_delivery_at_date([(self.table, 100)], date)

        date = today - relativedelta(days=60)
        self._create_and_process_delivery_at_date([(self.table, 90)], date)

        date = today - relativedelta(years=2)
        self._create_and_process_delivery_at_date([(self.table, 4)], date)

        date = today
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        self._create_and_process_delivery_at_date(
            [(self.table, 10)], date, to_validate=False
        )

        self.env.company.manufacturing_period_to_display_year = 5
        table_suggestion_wizard = self.env[
            "wizard.mrp.production.schedule.update.forecast"
        ].create(
            {
                "mrp_mps_id": self.mps_table.id,
            }
        )
        table_suggestion_wizard.based_on = "last_year"
        table_suggestion_wizard.with_context(
            {"period_scale": "year"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="year"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_year):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 105)
            elif i == 1:
                self.assertEqual(table_forecast["forecast_qty"], 110)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.based_on = "actual_demand"
        table_suggestion_wizard.with_context(
            {"period_scale": "year"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="year"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_year):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 120)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.based_on = "30_days"
        table_suggestion_wizard.with_context(
            {"period_scale": "year"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="year"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_year):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 1200)

        table_suggestion_wizard.based_on = "three_months"
        table_suggestion_wizard.with_context(
            {"period_scale": "year"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="year"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_year):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 760)

        table_suggestion_wizard.based_on = "one_year"
        table_suggestion_wizard.with_context(
            {"period_scale": "year"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="year"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_year):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 205)

    @freeze_time("2024-02-14")
    def test_suggestion_for_months_with_no_period(self):

        today = datetime.now().date()
        self.table.uom_id.rounding = 1.0

        date = today - relativedelta(years=1)
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        date = today - relativedelta(months=10)
        self._create_and_process_delivery_at_date([(self.table, 5)], date)

        date = today - relativedelta(days=20)
        self._create_and_process_delivery_at_date([(self.table, 100)], date)

        date = today - relativedelta(days=60)
        self._create_and_process_delivery_at_date([(self.table, 90)], date)

        date = today - relativedelta(years=2)
        self._create_and_process_delivery_at_date([(self.table, 4)], date)

        date = today
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        self._create_and_process_delivery_at_date(
            [(self.table, 10)], date, to_validate=False
        )

        self.env.company.manufacturing_period_to_display_month = 25
        table_suggestion_wizard = self.env[
            "wizard.mrp.production.schedule.update.forecast"
        ].create(
            {
                "mrp_mps_id": self.mps_table.id,
            }
        )
        table_suggestion_wizard.based_on = "last_year"
        table_suggestion_wizard.with_context(
            {"period_scale": "month"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="month"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_month):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            elif i == 2:
                self.assertEqual(table_forecast["forecast_qty"], 5)
            elif i == 10:
                self.assertEqual(table_forecast["forecast_qty"], 90)
            elif i == 11:
                self.assertEqual(table_forecast["forecast_qty"], 100)
            elif i == 12:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.based_on = "actual_demand"
        table_suggestion_wizard.with_context(
            {"period_scale": "month"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="month"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_month):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 20)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.based_on = "30_days"
        table_suggestion_wizard.with_context(
            {"period_scale": "month"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="month"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_month):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 100)

        table_suggestion_wizard.based_on = "three_months"
        table_suggestion_wizard.with_context(
            {"period_scale": "month"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="month"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_month):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 64)

        table_suggestion_wizard.based_on = "one_year"
        table_suggestion_wizard.with_context(
            {"period_scale": "month"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="month"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_month):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 18)

    @freeze_time("2024-02-14")
    def test_suggestion_for_weeks_with_no_period(self):

        today = datetime.now().date()
        based_on_year = today.year - 1
        self.table.uom_id.rounding = 1.0

        date = start_of(subtract(today, years=today.year - based_on_year), "week")
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        date = start_of(subtract(today, weeks=3), "week")
        self._create_and_process_delivery_at_date([(self.table, 100)], date)

        date = start_of(subtract(today, weeks=9), "week")
        self._create_and_process_delivery_at_date([(self.table, 90)], date)

        date = start_of(
            subtract(today, years=today.year - based_on_year, weeks=2), "week"
        )
        self._create_and_process_delivery_at_date([(self.table, 5)], date)

        date = start_of(today, "week")
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        self._create_and_process_delivery_at_date(
            [(self.table, 10)], date, to_validate=False
        )

        self.env.company.manufacturing_period_to_display_week = 105
        table_suggestion_wizard = self.env[
            "wizard.mrp.production.schedule.update.forecast"
        ].create(
            {
                "mrp_mps_id": self.mps_table.id,
            }
        )
        table_suggestion_wizard.based_on = "last_year"
        table_suggestion_wizard.with_context(
            {"period_scale": "week"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="week"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_week):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            elif i == 49:
                self.assertEqual(table_forecast["forecast_qty"], 100)
            elif i == 43:
                self.assertEqual(table_forecast["forecast_qty"], 90)
            elif i == 52:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.based_on = "actual_demand"
        table_suggestion_wizard.with_context(
            {"period_scale": "week"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="week"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_week):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 20)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.based_on = "30_days"
        table_suggestion_wizard.with_context(
            {"period_scale": "week"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="week"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_week):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 28)

        table_suggestion_wizard.based_on = "three_months"
        table_suggestion_wizard.with_context(
            {"period_scale": "week"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="week"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_week):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 17)

        table_suggestion_wizard.based_on = "one_year"
        table_suggestion_wizard.with_context(
            {"period_scale": "week"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="week"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_week):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 5)

    @freeze_time("2024-02-26")
    def test_suggestion_for_days_with_no_period(self):
        today = datetime.now().date()
        self.table.uom_id.rounding = 1.0

        date = today - relativedelta(years=1)
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        date = today - relativedelta(years=1, days=2)
        self._create_and_process_delivery_at_date([(self.table, 5)], date)

        date = today - relativedelta(days=20)
        self._create_and_process_delivery_at_date([(self.table, 100)], date)

        date = today - relativedelta(days=60)
        self._create_and_process_delivery_at_date([(self.table, 90)], date)

        date = today
        self._create_and_process_delivery_at_date([(self.table, 10)], date)

        self._create_and_process_delivery_at_date(
            [(self.table, 10)], date, to_validate=False
        )

        self.env.company.manufacturing_period_to_display_day = 365
        table_suggestion_wizard = self.env[
            "wizard.mrp.production.schedule.update.forecast"
        ].create(
            {
                "mrp_mps_id": self.mps_table.id,
            }
        )
        table_suggestion_wizard.based_on = "last_year"
        table_suggestion_wizard.with_context(
            {"period_scale": "day"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="day"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_day):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            elif i == 345:
                self.assertEqual(table_forecast["forecast_qty"], 100)
            elif i == 305:
                self.assertEqual(table_forecast["forecast_qty"], 90)
            elif i == 365:
                self.assertEqual(table_forecast["forecast_qty"], 10)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.based_on = "actual_demand"
        table_suggestion_wizard.with_context(
            {"period_scale": "day"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="day"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_day):
            table_forecast = mps_table["forecast_ids"][i]
            if i == 0:
                self.assertEqual(table_forecast["forecast_qty"], 20)
            else:
                self.assertEqual(table_forecast["forecast_qty"], 0)

        table_suggestion_wizard.based_on = "30_days"
        table_suggestion_wizard.with_context(
            {"period_scale": "day"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="day"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_day):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 4)

        table_suggestion_wizard.based_on = "three_months"
        table_suggestion_wizard.with_context(
            {"period_scale": "day"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="day"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_day):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 3)

        table_suggestion_wizard.based_on = "one_year"
        table_suggestion_wizard.with_context(
            {"period_scale": "day"}
        ).apply_forecast_quantity_suggestion()
        mps_table = self.mps_table.get_production_schedule_view_state(
            period_scale="day"
        )[0]
        for i in range(self.env.company.manufacturing_period_to_display_day):
            table_forecast = mps_table["forecast_ids"][i]
            self.assertEqual(table_forecast["forecast_qty"], 1)

    def test_a_company_write_naming_a_field_the_company_does_not_carry_is_not_a_display_toggle(
        self,
    ):
        company = self.env["res.company"]
        self.assertFalse(company._is_field_mps_display_group("leave_timesheet_task_id"))
        self.assertTrue(
            company._is_field_mps_display_group(
                "mrp_mps_show_actual_demand_year_minus_2"
            )
        )

    def test_a_batch_size_does_not_round_the_replenishment_up(self):
        self.mps_table.bom_id = self.bom_table
        self.bom_table.write({"enable_batch_size": True, "batch_size": 10})
        self.mps_table.write({"forecast_target_qty": 0, "min_to_replenish_qty": 0})
        self.assertEqual(self.mps_table._get_replenish_qty(-3), 3)
