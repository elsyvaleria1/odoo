from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestDeviceIsAnAsset(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        template = cls.env["product.template"].create(
            {
                "name": "Company phone",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("resource_asset.kind_it").id,
            }
        )
        cls.lot = cls.env["product.trace"].create(
            {
                "name": "PHONE-1",
                "product_id": template.product_variant_ids[0].id,
                "imei": "356938035643809",
            }
        )
        cls.asset = cls.lot.asset_id
        cls.env["resource.identifier"].create(
            {
                "resource_id": cls.asset.resource_id.id,
                "type_id": cls.env.ref("resource.identifier_type_serial").id,
                "value": "PHONE-1-SN",
            }
        )
        cls.category = cls.env.ref("device.device_category_generic")
        cls.config = cls.env["device.profile"].create(
            {"name": "Probe config", "protocol": "http"}
        )

    def _device(self, **vals):
        vals.setdefault("name", "Probe device")
        vals.setdefault(
            "identifier", f"PROBE-{len(self.env['device.device'].search([]))}"
        )
        vals.setdefault("device_category_id", self.category.id)
        vals.setdefault("config_id", self.config.id)
        vals.setdefault("comm_protocol", "http")
        vals.setdefault("endpoint", "192.0.2.10")
        return self.env["device.device"].create(vals)

    def test_resource_pointer_projects_the_asset_and_identifier(self):
        device = self._device(resource_id=self.asset.resource_id.id)
        self.assertEqual(device.own_asset_id, self.asset)
        self.assertEqual(device.imei, self.lot.imei)
        self.assertIn(device, self.asset.device_ids)
        self.assertIn(
            device,
            self.env["device.device"].search([("own_asset_id", "=", self.asset.id)]),
        )
        device.own_asset_id = False
        self.assertFalse(device.resource_id)
        device.own_asset_id = self.asset
        self.assertEqual(device.resource_id, self.asset.resource_id)

    def test_asset_projection_does_not_require_an_asset(self):
        resource = self.env["resource.resource"].create(
            {"name": "Unregistered hardware", "type": "material", "tz": "UTC"}
        )
        device = self._device(resource_id=resource.id)
        self.assertFalse(device.own_asset_id)
        device.own_asset_id = False
        self.assertEqual(device.resource_id, resource)

    def test_conflicting_identity_inputs_are_rejected(self):
        resource = self.env["resource.resource"].create(
            {"name": "Other hardware", "type": "material", "tz": "UTC"}
        )
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._device(own_asset_id=self.asset.id, resource_id=resource.id)
        device = self._device()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            device.write({"own_asset_id": self.asset.id, "resource_id": resource.id})
        self.assertFalse(device.resource_id)

    def test_default_asset_reuses_its_existing_resource(self):
        device = (
            self.env["device.device"]
            .with_context(default_own_asset_id=self.asset.id)
            .create({"name": "Default asset", "identifier": "DEFAULT-ASSET"})
        )
        self.assertEqual(device.resource_id, self.asset.resource_id)
        self.assertEqual(device.own_asset_id, self.asset)

    def test_representation_changes_do_not_change_the_gps_target(self):
        if "gps_device_id" not in self.env["resource.resource"]._fields:
            self.skipTest("GPS telemetry is optional")
        device = self._device(own_asset_id=self.asset.id)
        target = self.env["resource.resource"].create(
            {
                "name": "Observed machine",
                "type": "material",
                "tz": "Europe/Paris",
                "gps_device_id": device.id,
            }
        )
        self.assertEqual(device.tracked_resource_id, target)
        self.assertEqual(device.resource_id, self.asset.resource_id)
        self.assertEqual(device._gps_timezone(), "Europe/Paris")
        device.own_asset_id = False
        self.assertEqual(device.tracked_resource_id, target)
        self.assertEqual(target.gps_device_id, device)
        self.assertFalse(device.resource_id)

    def test_linking_an_asset_gives_the_device_its_identity(self):
        device = self._device(own_asset_id=self.asset.id)
        self.assertEqual(device.imei, "356938035643809")
        self.assertEqual(device.serial_number, "PHONE-1-SN")

    def test_an_unlinked_device_keeps_its_own_identity(self):
        device = self._device(imei="111111111111111")
        self.assertEqual(device.imei, "111111111111111")
        self.assertFalse(device.own_asset_id)

    def test_linking_does_not_erase_what_the_asset_does_not_declare(self):
        device = self._device(plate="OWN-PLATE", own_asset_id=self.asset.id)
        self.assertFalse(self.lot.license_plate)
        self.assertEqual(
            device.plate,
            "OWN-PLATE",
            "the asset is the source of truth only for what it actually declares",
        )

    def test_the_asset_is_the_single_source_of_truth(self):
        device = self._device(own_asset_id=self.asset.id)
        with self.assertRaises(ValidationError):
            device.imei = "999999999999999"
            device.flush_recordset()

    def test_editing_the_asset_moves_the_device(self):
        device = self._device(own_asset_id=self.asset.id)
        self.lot.imei = "356938035643810"
        device.invalidate_recordset()
        self.assertEqual(device.imei, "356938035643810")

    def test_an_asset_lists_the_devices_that_are_it(self):
        resources_before = (
            self.env["resource.resource"]
            .with_context(active_test=False)
            .search_count([])
        )
        first = self._device(own_asset_id=self.asset.id)
        second = self._device(name="Second probe", own_asset_id=self.asset.id)
        self.asset.invalidate_recordset()
        self.assertEqual(self.asset.device_ids, first + second)
        self.assertEqual(self.asset.count_device_devices, 2)
        self.assertEqual(
            first.own_asset_id.resource_id, second.own_asset_id.resource_id
        )
        self.assertEqual(
            self.env["resource.resource"]
            .with_context(active_test=False)
            .search_count([]),
            resources_before,
            "Several endpoints of one physical asset do not create new identities",
        )

    def test_physical_components_keep_independent_resource_identity(self):
        component = (
            self.env["product.trace"]
            .create(
                {
                    "name": "PHONE-COMPONENT",
                    "product_id": self.lot.product_id.id,
                    "imei": "356938035643811",
                }
            )
            .asset_id
        )
        component.parent_id = self.asset
        parent_resource = self.asset.resource_id
        component_resource = component.resource_id
        self.assertNotEqual(parent_resource, component_resource)
        parent_resource.write({"capacity": 3, "tz": "Asia/Tokyo"})
        component_resource.write({"capacity": 2, "tz": "Europe/Paris"})
        parent_device = self._device(own_asset_id=self.asset.id)
        component_device = self._device(
            own_asset_id=component.id, parent_id=parent_device.id
        )
        self.assertEqual(parent_device.own_asset_id.resource_id, parent_resource)
        self.assertEqual(component_device.own_asset_id.resource_id, component_resource)
        self.assertEqual(parent_resource.capacity, 3)
        self.assertEqual(component_resource.capacity, 2)
        self.assertEqual(parent_resource.tz, "Asia/Tokyo")
        self.assertEqual(component_resource.tz, "Europe/Paris")
        component.parent_id = False
        self.assertEqual(component.resource_id, component_resource)
        self.assertEqual(self.asset.resource_id, parent_resource)

    def test_endpoint_structure_does_not_reparent_physical_assets(self):
        first = self._device(own_asset_id=self.asset.id)
        second = self._device(own_asset_id=self.asset.id, parent_id=first.id)
        resource = self.asset.resource_id
        self.assertEqual(second.parent_id, first)
        self.assertFalse(self.asset.parent_id)
        self.assertEqual(second.own_asset_id.resource_id, resource)
        second.parent_id = False
        self.assertEqual(second.own_asset_id.resource_id, resource)
        self.assertEqual(first.own_asset_id.resource_id, resource)

    def test_deleting_endpoint_tree_keeps_physical_resource(self):
        first = self._device(own_asset_id=self.asset.id)
        second = self._device(own_asset_id=self.asset.id, parent_id=first.id)
        resource = self.asset.resource_id
        first.unlink()
        self.assertFalse((first + second).exists())
        self.assertTrue(self.asset.exists())
        self.assertEqual(self.asset.resource_id, resource)
        self.assertTrue(resource.exists())
