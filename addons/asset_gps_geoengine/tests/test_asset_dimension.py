import ast
import pathlib

from odoo.tests import common


class TestGeoengineKnowsNothingOfAssets(common.TransactionCase):

    def test_the_geospatial_layer_names_no_asset_or_hr_model(self):
        root = pathlib.Path(__file__).resolve().parents[2] / "device_gps_geoengine"
        offenders = {}
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or "migrations" in path.parts:
                continue
            source = path.read_text()
            named = [
                model
                for model in ("product.trace", "hr.employee", "resource.log")
                if model in source
            ]
            if named:
                offenders[str(path.relative_to(root))] = named
        self.assertFalse(
            offenders,
            "device_gps_geoengine draws devices, points and parcels. Anything "
            "that knows what a vehicle or a driver is belongs in "
            f"asset_gps_geoengine: {offenders}",
        )

    def test_the_geospatial_manifest_depends_on_neither(self):
        root = pathlib.Path(__file__).resolve().parents[2] / "device_gps_geoengine"
        manifest = ast.literal_eval((root / "__manifest__.py").read_text())
        self.assertEqual(
            [
                name
                for name in manifest["depends"]
                if name.startswith(("asset", "resource_asset", "hr"))
            ],
            [],
            "device_gps_geoengine may geocode, never know an asset or a driver",
        )


class TestAssetDimension(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create({"name": "Trail Bridge Config"})
        cls.device = cls.env["device.device"].create(
            {
                "name": "GPS-TRAIL-01",
                "identifier": "GPS-TRAIL-01",
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "endpoint": "10.0.0.9",
                "is_gps_device": True,
            }
        )
        cls.manufacturer = cls.env["res.partner"].create(
            {"name": "Trail Bridge Motors", "is_manufacturer": True}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Trail Bridge Truck",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("base.kind_vehicle").id,
                "manufacturer_id": cls.manufacturer.id,
                "company_id": cls.env.company.id,
            }
        )
        cls.canonical = "Trail Bridge Motors / Trail Bridge Truck / TRL-001"
        cls.operator = cls.env["hr.employee"].create({"name": "Trail Bridge Driver"})
        cls.asset = cls.env["product.trace"].create(
            {
                "name": "TRAIL-ASSET-01",
                "product_id": cls.product.id,
                "license_plate": "TRL-001",
                "gps_device_id": cls.device.id,
                "operator_id": cls.operator.id,
            }
        )

    def _wizard(self, **overrides):
        vals = {
            "selection_mode": "asset",
            "asset_ids": [(6, 0, self.asset.asset_id.ids)],
        }
        vals.update(overrides)
        return self.env["wizard.device.device.view.trail"].create(vals)

    def test_the_bridge_restores_both_selection_modes(self):
        selection = dict(
            self.env["wizard.device.device.view.trail"]
            ._fields["selection_mode"]
            .get_description(self.env)["selection"]
        )
        self.assertEqual(set(selection), {"asset", "operator", "device"})

    def test_selecting_by_asset_resolves_to_its_device(self):
        self.assertEqual(self._wizard().resolved_device_ids, self.device)

    def test_selecting_by_operator_resolves_to_their_assets_device(self):
        wizard = self._wizard(
            selection_mode="operator",
            asset_ids=False,
            operator_ids=[(6, 0, self.operator.ids)],
        )
        self.assertEqual(wizard.resolved_device_ids, self.device)

    def test_selecting_by_device_still_works_through_super(self):
        wizard = self._wizard(
            selection_mode="device",
            asset_ids=False,
            device_ids=[(6, 0, self.device.ids)],
        )
        self.assertEqual(wizard.resolved_device_ids, self.device)

    def test_a_trail_carries_the_vehicle_and_the_driver(self):
        source_info = self._wizard()._prepare_source_mapping()[self.device.id]
        self.assertEqual(source_info["asset_id"], self.asset.asset_id.id)
        self.assertEqual(source_info["operator_id"], self.operator.id)
        self.assertEqual(source_info["license_plate"], "TRL-001")

        vals = self._wizard()._trail_result_vals(source_info)
        self.assertEqual(vals["asset_id"], self.asset.asset_id.id)
        self.assertEqual(vals["operator_id"], self.operator.id)

    def test_the_trail_is_named_for_the_driver_and_the_vehicle(self):
        wizard = self._wizard()
        name = wizard._get_trail_display_name(
            wizard._prepare_source_mapping()[self.device.id]
        )
        self.assertIn(self.operator.name, name)
        self.assertIn("TRL-001", name)

    def test_the_empty_selection_message_names_what_was_selected(self):
        wizard = self._wizard(asset_ids=False)
        self.assertIn("asset", wizard._empty_selection_message())

    def test_the_map_label_becomes_the_driver_and_the_vehicle(self):
        self.assertEqual(self.device.map_title, self.operator.name)
        self.assertEqual(self.device.map_subtitle, self.canonical)

    def test_a_vehicle_with_no_driver_is_named_by_the_vehicle(self):
        self.asset.operator_id = False
        self.assertFalse(self.device.asset_operator_id)
        self.assertEqual(self.device.map_title, self.canonical)
        self.assertFalse(self.device.map_subtitle)

    def test_a_vehicle_with_no_plate_is_still_named(self):
        self.asset.license_plate = False
        self.assertEqual(self.device.map_title, self.operator.name)
        self.assertEqual(
            self.device.map_subtitle,
            "Trail Bridge Motors / Trail Bridge Truck / TRAIL-ASSET-01",
        )

    def test_the_label_is_the_canonical_name_not_the_typed_one(self):
        self.asset.name = "JAANMR856C7500651 TRL-001 100"
        self.assertEqual(self.device.map_subtitle, self.canonical)

    def test_the_plate_is_not_said_twice(self):
        self.assertEqual(self.device.map_subtitle.count("TRL-001"), 1)

    def test_an_asset_that_is_not_a_vehicle_still_gets_its_plate(self):
        pump = self.env["product.product"].create(
            {
                "name": "Trail Bridge Pump",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": self.env.ref("base.kind_equipment").id,
                "company_id": self.env.company.id,
            }
        )
        device = self.env["device.device"].create(
            {
                "name": "GPS-PUMP-01",
                "identifier": "GPS-PUMP-01",
                "config_id": self.config.id,
                "comm_protocol": "http",
                "endpoint": "10.0.0.12",
            }
        )
        self.env["product.trace"].create(
            {
                "name": "PUMP-ASSET-01",
                "product_id": pump.id,
                "license_plate": "PMP-002",
                "gps_device_id": device.id,
            }
        )
        self.assertEqual(device.map_title, "Trail Bridge Pump PUMP-ASSET-01 (PMP-002)")

    def test_a_device_on_no_asset_keeps_the_base_label(self):
        loose = self.env["device.device"].create(
            {
                "name": "GPS-LOOSE",
                "identifier": "GPS-LOOSE",
                "config_id": self.config.id,
                "comm_protocol": "http",
                "endpoint": "10.0.0.10",
            }
        )
        self.assertEqual(loose.map_title, "GPS-LOOSE")
        self.assertFalse(loose.map_subtitle)
