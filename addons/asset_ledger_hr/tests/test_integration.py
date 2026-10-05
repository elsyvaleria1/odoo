from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase

from odoo.addons.asset_ledger.tests.common import (
    create_test_product,
    create_test_template,
    ensure_publish_date_field,
)


class TestAssetManagementWorkflows(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_publish_date_field(cls.env)
        cls.ProductTrace = cls.env["product.trace"]
        cls.ProductAssetLog = cls.env["resource.log"]
        cls.ProductTemplate = cls.env["product.template"]
        cls.ProductProduct = cls.env["product.product"]
        cls.HrEmployee = cls.env["hr.employee"]
        cls.Partner = cls.env["res.partner"]

        cls.driver1 = cls.HrEmployee.create(
            {
                "name": "Driver One",
                "company_id": cls.env.company.id,
            }
        )
        cls.driver2 = cls.HrEmployee.create(
            {
                "name": "Driver Two",
                "company_id": cls.env.company.id,
            }
        )
        cls.fleet_manager = cls.HrEmployee.create(
            {
                "name": "Fleet Manager",
                "company_id": cls.env.company.id,
            }
        )

        cls.fuel_vendor = cls.Partner.create(
            {
                "name": "Gas Station XYZ",
                "is_company": True,
            }
        )
        cls.maintenance_vendor = cls.Partner.create(
            {
                "name": "Auto Repair Shop",
                "is_company": True,
            }
        )
        cls.insurance_vendor = cls.Partner.create(
            {
                "name": "Insurance Company",
                "is_company": True,
            }
        )

        cls.vehicle_template = create_test_template(
            cls.env,
            name="Delivery Truck",
            asset_kind="vehicle",
            fuel_tank_capacity=100,
            fuel_efficiency_theoretical=10.0,
            power=300,
            type="consu",
            tracking="serial",
        )
        cls.vehicle_product = cls.vehicle_template.product_variant_id

        try:
            fuel_categ = cls.env.ref("asset_ledger.product_category_fuel")
            toll_categ = cls.env.ref("asset_ledger.product_category_highway_toll")
        except ValueError:
            parent_categ = cls.env["product.category"].create({"name": "Services"})
            fuel_categ = cls.env["product.category"].create(
                {
                    "name": "Fuel",
                    "parent_id": parent_categ.id,
                }
            )
            toll_categ = cls.env["product.category"].create(
                {
                    "name": "Highway Toll",
                    "parent_id": parent_categ.id,
                }
            )

        cls.fuel_product = create_test_product(
            cls.env,
            name="Diesel",
            categ_id=fuel_categ.id,
            type="service",
        )
        cls.toll_product = create_test_product(
            cls.env,
            name="Toll Payment",
            categ_id=toll_categ.id,
            type="service",
        )
        cls.maintenance_product = create_test_product(
            cls.env,
            name="Preventive Maintenance",
            type="service",
        )
        cls.insurance_product = create_test_product(
            cls.env,
            name="Vehicle Insurance",
            type="service",
        )

    def test_complete_vehicle_lifecycle(self):
        vehicle = self.ProductTrace.create(
            {
                "name": "VIN-TRUCK-001",
                "product_id": self.vehicle_product.id,
                "license_plate": "HRT-0001",
                "vin_sn": "1HGBH41JXMN109187",
                "engine_sn": "ENG-12345",
                "date_acquisition": fields.Date.today(),
                "value_original": 75000.0,
                "brand_new": True,
                "asset_manager_id": self.fleet_manager.id,
                "operator_id": self.driver1.id,
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(vehicle.license_plate, "HRT-0001")
        self.assertEqual(vehicle.operator_id, self.driver1)
        self.assertEqual(vehicle.asset_manager_id, self.fleet_manager)

        assignment_logs = self.ProductAssetLog.search(
            [
                ("trace_id", "=", vehicle.id),
            ]
        )
        self.assertGreater(len(assignment_logs), 0)

        start_date = fields.Date.today()
        end_date = start_date + timedelta(days=365)

        insurance_log = self.ProductAssetLog.create(
            {
                "asset_id": vehicle.asset_id.id,
                "product_id": self.insurance_product.id,
                "vendor_id": self.insurance_vendor.id,
                "state": "running",
                "date_start": start_date,
                "date_end": end_date,
                "amount": 3000.0,
                "inv_ref": "INS-2024-001",
            }
        )

        self.assertEqual(insurance_log.state, "running")
        self.assertEqual(insurance_log.operator_id, self.driver1)
        self.assertEqual(insurance_log.asset_manager_id, self.fleet_manager)

        self.ProductAssetLog.create(
            {
                "asset_id": vehicle.asset_id.id,
                "product_id": self.fuel_product.id,
                "vendor_id": self.fuel_vendor.id,
                "amount": 800.0,
                "qty_fuel": 80.0,
                "efficiency": 10.5,
                "odometer": 1000.0,
                "state": "done",
            }
        )

        vehicle.invalidate_recordset()
        self.assertEqual(vehicle.asset_id.odometer, 1000.0)

        self.ProductAssetLog.create(
            {
                "asset_id": vehicle.asset_id.id,
                "product_id": self.toll_product.id,
                "amount": 150.0,
                "odometer": 1500.0,
                "state": "done",
            }
        )

        vehicle.invalidate_recordset()
        self.assertEqual(vehicle.asset_id.odometer, 1500.0)

        vehicle.write({"operator_id": self.driver2.id})

        assignment_logs = self.ProductAssetLog.search(
            [
                ("trace_id", "=", vehicle.id),
            ]
        )
        self.assertGreaterEqual(len(assignment_logs), 2)

        maintenance_log = self.ProductAssetLog.create(
            {
                "asset_id": vehicle.asset_id.id,
                "product_id": self.maintenance_product.id,
                "vendor_id": self.maintenance_vendor.id,
                "amount": 1500.0,
                "odometer": 5000.0,
                "state": "done",
                "notes": "Oil change and tire rotation",
            }
        )

        self.assertEqual(maintenance_log.operator_id, self.driver2)
        self.assertEqual(maintenance_log.asset_manager_id, self.fleet_manager)

        vehicle.invalidate_recordset()
        self.assertEqual(vehicle.asset_id.odometer, 5000.0)

        vehicle.invalidate_recordset()
        self.assertEqual(vehicle.asset_id.count_logs_service, 0)
        self.assertGreaterEqual(vehicle.asset_id.count_logs_all, 4)

    def test_operator_transfer_workflow(self):
        vehicle1 = self.ProductTrace.create(
            {
                "name": "VAN-001",
                "product_id": self.vehicle_product.id,
                "license_plate": "VAN-001",
                "operator_id": self.driver1.id,
                "company_id": self.env.company.id,
            }
        )

        vehicle2 = self.ProductTrace.create(
            {
                "name": "VAN-002",
                "product_id": self.vehicle_product.id,
                "license_plate": "VAN-002",
                "operator_id": self.driver2.id,
                "company_id": self.env.company.id,
            }
        )

        vehicle1.write({"future_operator_id": self.driver2.id})

        self.assertEqual(vehicle1.operator_id, self.driver1)
        self.assertEqual(vehicle1.future_operator_id, self.driver2)

        vehicle1.action_accept_operator_change()

        self.assertEqual(vehicle1.operator_id, self.driver2)
        self.assertFalse(vehicle1.future_operator_id)

        vehicle2.invalidate_recordset()
        self.assertFalse(vehicle2.operator_id)

    def test_multi_vehicle_fleet_tracking(self):
        vehicles = []

        for i in range(5):
            vehicle = self.ProductTrace.create(
                {
                    "name": f"FLEET-{i + 1:03d}",
                    "product_id": self.vehicle_product.id,
                    "license_plate": f"FLT-{i + 1:03d}",
                    "operator_id": (self.driver1.id if i % 2 == 0 else self.driver2.id),
                    "asset_manager_id": self.fleet_manager.id,
                    "company_id": self.env.company.id,
                }
            )
            vehicles.append(vehicle)

        for vehicle in vehicles:
            self.ProductAssetLog.create(
                {
                    "asset_id": vehicle.asset_id.id,
                    "product_id": self.fuel_product.id,
                    "amount": 500.0 + (vehicle.id % 100),
                    "odometer": 1000.0 * (vehicle.id % 10),
                    "state": "done",
                }
            )

            self.ProductAssetLog.create(
                {
                    "asset_id": vehicle.asset_id.id,
                    "product_id": self.insurance_product.id,
                    "state": "running",
                    "date_end": fields.Date.today()
                    + timedelta(days=180 + (vehicle.id % 90)),
                    "amount": 2000.0,
                }
            )

        for vehicle in vehicles:
            vehicle.invalidate_recordset()
            self.assertGreaterEqual(vehicle.asset_id.count_logs_all, 2)
            self.assertEqual(vehicle.asset_id.count_logs_service, 0)

        driver1_vehicles = self.ProductTrace.search(
            [
                ("id", "in", [v.id for v in vehicles]),
                ("operator_id", "=", self.driver1.id),
            ]
        )
        driver2_vehicles = self.ProductTrace.search(
            [
                ("id", "in", [v.id for v in vehicles]),
                ("operator_id", "=", self.driver2.id),
            ]
        )

        self.assertEqual(len(driver1_vehicles), 3)
        self.assertEqual(len(driver2_vehicles), 2)

    def test_odometer_tracking_across_logs(self):
        vehicle = self.ProductTrace.create(
            {
                "name": "ODO-TEST",
                "product_id": self.vehicle_product.id,
                "license_plate": "ODO-001",
                "company_id": self.env.company.id,
            }
        )

        self.assertEqual(vehicle.asset_id.odometer, 0.0)

        odometer_values = [1000, 2500, 2000, 5000, 4500, 7000]

        for odo in odometer_values:
            self.ProductAssetLog.create(
                {
                    "asset_id": vehicle.asset_id.id,
                    "product_id": self.fuel_product.id,
                    "odometer": odo,
                    "amount": 100.0,
                    "state": "done",
                }
            )

        vehicle.invalidate_recordset()
        self.assertEqual(vehicle.asset_id.odometer, 7000.0)

    def test_view_actions_integration(self):
        vehicle = self.ProductTrace.create(
            {
                "name": "VIEW-TEST",
                "product_id": self.vehicle_product.id,
                "operator_id": self.driver1.id,
                "company_id": self.env.company.id,
            }
        )

        self.ProductAssetLog.create(
            {
                "asset_id": vehicle.asset_id.id,
                "product_id": self.fuel_product.id,
                "amount": 100.0,
                "state": "done",
            }
        )
        self.ProductAssetLog.create(
            {
                "asset_id": vehicle.asset_id.id,
                "product_id": self.toll_product.id,
                "amount": 50.0,
                "state": "done",
            }
        )
        self.ProductAssetLog.create(
            {
                "asset_id": vehicle.asset_id.id,
                "product_id": self.insurance_product.id,
                "state": "running",
            }
        )

        service_action = vehicle.action_view_logs_service()
        self.assertIn("domain", service_action)

        assignment_action = vehicle.action_view_logs_assignation()
        self.assertIn("domain", assignment_action)

        all_action = vehicle.action_view_logs_all()
        self.assertEqual(all_action["domain"], [("asset_id", "=", vehicle.asset_id.id)])
