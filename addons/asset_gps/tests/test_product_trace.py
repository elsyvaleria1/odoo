from types import SimpleNamespace

from freezegun import freeze_time

from odoo.exceptions import ValidationError

from ..tools.actions import prepare_gps_device_action
from .common import ProductAssetRemoteCommon


class StockLotGpsTestBase(ProductAssetRemoteCommon):
    @classmethod
    @freeze_time("2026-01-01")
    def setUpClass(cls):
        super().setUpClass()
        cls.device = cls.env["device.device"].create(
            {
                "name": "Test GPS Tracker",
                "serial_number": "GPS-LOT-001",
                "identifier": "GPS-LOT-001",
                "credential_id": False,
                "config_id": cls.config.id,
            }
        )

        cls.vehicle = cls.env["product.trace"].create(
            {
                "name": "LOT-GPS-VH",
                "product_id": cls.product.id,
                "company_id": cls.company.id,
                "odometer_uom_id": cls.km_uom.id,
                "gps_device_id": cls.device.id,
            }
        )


class TestStockLotGpsFields(StockLotGpsTestBase):
    def test_gps_device_id_field_exists(self):
        field = self.env["product.trace"]._fields.get("gps_device_id")

        self.assertIsNotNone(field)
        self.assertEqual(field.comodel_name, "device.device")

    def test_related_fields_exist(self):
        expected_fields = [
            "gps_battery_level",
            "gps_connection_state",
            "gps_current_speed",
            "gps_date_last_data",
            "gps_ignition_state",
            "gps_movement_state",
            "gps_tracking_enabled",
        ]
        lot_fields = self.env["product.trace"]._fields

        for fname in expected_fields:
            with self.subTest(field=fname):
                self.assertIn(
                    fname, lot_fields, f"Field {fname} missing on product.trace"
                )
                self.assertTrue(
                    lot_fields[fname].related, f"Field {fname} is not related"
                )

    def test_related_fields_empty_without_device(self):
        lot_no_gps = self.env["product.trace"].create(
            {
                "name": "LOT-NO-GPS",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
            }
        )

        self.assertFalse(lot_no_gps.gps_device_id)
        self.assertFalse(lot_no_gps.gps_battery_level)
        self.assertFalse(lot_no_gps.gps_connection_state)
        self.assertFalse(lot_no_gps.gps_tracking_enabled)


class TestStockLotGpsConstraint(StockLotGpsTestBase):
    def test_unique_gps_device_raises_on_duplicate(self):
        with self.assertRaises(ValidationError):
            self.env["product.trace"].create(
                {
                    "name": "LOT-DUPLICATE-GPS",
                    "product_id": self.product.id,
                    "company_id": self.company.id,
                    "odometer_uom_id": self.km_uom.id,
                    "gps_device_id": self.device.id,
                }
            )

    def test_different_gps_devices_allowed(self):
        second_device = self.env["device.device"].create(
            {
                "name": "Second GPS Tracker",
                "serial_number": "GPS-LOT-002",
                "identifier": "GPS-LOT-002",
                "credential_id": False,
                "config_id": self.config.id,
            }
        )

        lot2 = self.env["product.trace"].create(
            {
                "name": "LOT-SECOND-GPS",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": second_device.id,
            }
        )

        self.assertEqual(lot2.gps_device_id, second_device)

    def test_null_gps_allowed_on_multiple_lots(self):
        lots = self.env["product.trace"]
        for i in range(3):
            lots |= self.env["product.trace"].create(
                {
                    "name": f"LOT-NO-GPS-{i}",
                    "product_id": self.product.id,
                    "company_id": self.company.id,
                    "odometer_uom_id": self.km_uom.id,
                }
            )

        self.assertEqual(len(lots), 3)
        self.assertFalse(any(lot.gps_device_id for lot in lots))


class TestStockLotGpsActions(StockLotGpsTestBase):
    def test_legacy_action_helper_accepts_a_name_only_carrier(self):
        carrier = SimpleNamespace(
            env=self.env,
            name="Legacy carrier",
            gps_device_id=self.device,
            check_singleton=lambda: None,
        )
        action = prepare_gps_device_action(carrier)
        self.assertEqual(action["name"], "GPS Device: Legacy carrier")
        self.assertEqual(action["res_id"], self.device.id)

    def test_legacy_navigation_helper_uses_the_shared_action(self):
        self.assertEqual(
            prepare_gps_device_action(self.vehicle),
            self.vehicle.action_view_gps_device(),
        )

    def test_asset_and_trace_open_the_same_device_with_their_own_titles(self):
        for owner in (self.vehicle, self.vehicle.asset_id):
            with self.subTest(model=owner._name):
                action = owner.action_view_gps_device()
                self.assertEqual(action["res_id"], self.device.id)
                self.assertEqual(
                    action["name"], owner.env._("GPS Device: %s") % owner.display_name
                )
                self.assertEqual(action["target"], "new")
        self.vehicle.gps_device_id = False
        for owner in (self.vehicle, self.vehicle.asset_id):
            with self.subTest(model=owner._name), self.assertRaises(ValidationError):
                owner.action_view_gps_device()

    def test_action_view_gps_device_returns_action(self):
        action = self.vehicle.action_view_gps_device()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "device.device")
        self.assertEqual(action["res_id"], self.device.id)
        self.assertEqual(action["view_mode"], "form")
        self.assertEqual(action["target"], "new")

    def test_action_view_gps_device_raises_without_device(self):
        lot_no_gps = self.env["product.trace"].create(
            {
                "name": "LOT-NO-GPS-ACTION",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
            }
        )

        with self.assertRaises(ValidationError):
            lot_no_gps.action_view_gps_device()

    def test_action_view_tracking_history_returns_action(self):
        action = self.vehicle.action_view_tracking_history()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "device.data.log.gps")
        self.assertIn(
            ("device_id", "=", self.device.id),
            action["domain"],
        )
        self.assertEqual(
            action["context"]["default_device_id"],
            self.device.id,
        )
        self.assertEqual(action["context"]["search_default_last_week"], 1)

    def test_action_view_tracking_history_asks_only_for_views_that_exist(self):
        action = self.vehicle.action_view_tracking_history()

        self.env[action["res_model"]].get_views(
            [(False, view_type) for view_type in action["view_mode"].split(",")]
        )

    def test_action_view_tracking_history_raises_without_device(self):
        lot_no_gps = self.env["product.trace"].create(
            {
                "name": "LOT-NO-GPS-HISTORY",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
            }
        )

        with self.assertRaises(ValidationError):
            lot_no_gps.action_view_tracking_history()
