from odoo.exceptions import ValidationError
from odoo.tests import new_test_user

from .common import ProductAssetRemoteCommon
from odoo.addons.asset_ledger.tests.common import create_test_product


class DeviceDeviceAssetTestBase(ProductAssetRemoteCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.DeviceDevice = cls.env["device.device"]


class TestRemoteDeviceAssetFields(DeviceDeviceAssetTestBase):
    def test_asset_user_can_reassign_tracker_without_resource_write_rights(self):
        user = new_test_user(
            self.env,
            login="tracker_asset_editor",
            groups="base.group_asset_manager,device_gps.group_device_gps_manager",
        )
        resource = self.env["resource.resource"].create(
            {"name": "Assigned elsewhere", "type": "material"}
        )
        target = self.env["resource.resource"].create(
            {
                "name": "Audit target",
                "kind_id": self.env.ref("base.kind_machinery").id,
            }
        )
        device = self.env["device.device"].create(
            {
                "name": "Audit tracker",
                "identifier": "audit_asset_editor",
                "config_id": self.config.id,
            }
        )
        self.assertFalse(resource.with_user(user).has_access("write"))
        self.assertTrue(target.with_user(user).has_access("write"))
        device.with_user(user).asset_id = target
        self.assertEqual(target.gps_device_id, device)

    def test_clearing_an_empty_asset_relation_preserves_a_non_asset_target(self):
        resource = self.env["resource.resource"].create(
            {"name": "Person target", "type": "human"}
        )
        device = self.env["device.device"].create(
            {
                "name": "Person tracker",
                "identifier": "audit_non_asset_target",
                "config_id": self.config.id,
            }
        )
        resource.gps_device_id = device
        self.assertFalse(device.asset_id)
        device.asset_id = False
        self.assertEqual(device.tracked_resource_id, resource)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vehicle = cls.env["product.trace"].create(
            {
                "name": "GPS-ASSET-VH",
                "product_id": cls.product.id,
                "company_id": cls.company.id,
                "odometer_uom_id": cls.km_uom.id,
            }
        )

    def test_tracking_is_owned_by_the_resource_identity(self):
        field = self.DeviceDevice._fields["asset_id"]

        self.assertEqual(field.comodel_name, "resource.resource")
        tracked_field = self.DeviceDevice._fields["tracked_resource_id"]
        self.assertTrue(tracked_field.is_one2one)
        self.assertEqual(tracked_field.inverse_name, "gps_device_id")
        resource_field = self.env["resource.resource"]._fields["gps_device_id"]
        self.assertEqual(resource_field.index, "unique")
        self.assertFalse(resource_field.related)
        self.assertTrue(resource_field.store)


class TestRemoteDeviceAssetComputation(DeviceDeviceAssetTestBase):
    def test_asset_id_reads_the_asset_that_names_the_device(self):
        device = self.DeviceDevice.create(
            {
                "name": "Test GPS Device",
                "serial_number": "GPS-TEST-001",
                "identifier": "GPS-TEST-001",
                "credential_id": False,
                "config_id": self.config.id,
            }
        )

        vehicle = self.env["product.trace"].create(
            {
                "name": "COMPUTE-VH",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": device.id,
            }
        )

        self.assertEqual(device.asset_id, vehicle.asset_id)

    def test_asset_id_empty_when_no_assets(self):
        device = self.DeviceDevice.create(
            {
                "name": "Unlinked Device",
                "serial_number": "GPS-UNLINKED",
                "identifier": "GPS-UNLINKED",
                "credential_id": False,
                "config_id": self.config.id,
            }
        )

        self.assertFalse(device.asset_id)

    def test_asset_id_survives_archiving_the_asset(self):
        device = self.DeviceDevice.create(
            {
                "name": "Archive Test Device",
                "serial_number": "GPS-ARCHIVE-001",
                "identifier": "GPS-ARCHIVE-001",
                "credential_id": False,
                "config_id": self.config.id,
            }
        )
        vehicle = self.env["product.trace"].create(
            {
                "name": "ARCHIVE-VH",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": device.id,
            }
        )
        self.assertEqual(device.asset_id, vehicle.asset_id)

        vehicle.asset_id.active = False
        device.invalidate_recordset(["asset_id"])

        self.assertEqual(
            device.asset_id,
            vehicle.asset_id,
            "the device is still physically installed on the archived asset",
        )
        self.assertEqual(
            device.action_view_tracked_asset()["res_id"],
            vehicle.asset_id.id,
            "and the action names a record the user can still open",
        )

    def test_asset_id_clears_when_the_asset_releases_the_device(self):
        device = self.DeviceDevice.create(
            {
                "name": "Release Test Device",
                "serial_number": "GPS-RELEASE-001",
                "identifier": "GPS-RELEASE-001",
                "credential_id": False,
                "config_id": self.config.id,
            }
        )
        vehicle = self.env["product.trace"].create(
            {
                "name": "RELEASE-VH",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": device.id,
            }
        )
        self.assertEqual(device.asset_id, vehicle.asset_id)

        vehicle.gps_device_id = False

        self.assertFalse(device.asset_id)


class TestRemoteDeviceOneAsset(DeviceDeviceAssetTestBase):
    def _device(self, name):
        return self.DeviceDevice.create(
            {
                "name": name,
                "serial_number": name,
                "identifier": name,
                "credential_id": False,
                "config_id": self.config.id,
            }
        )

    def test_a_device_is_installed_on_one_asset_across_kinds(self):
        device = self._device("GPS-ONE-001")
        machinery_product = create_test_product(
            self.env,
            name="Test Machinery Product",
            type="consu",
            tracking="serial",
            asset_kind="machinery",
        )
        vehicle = self.env["product.trace"].create(
            {
                "name": "ONE-VH",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": device.id,
            }
        )
        press = self.env["product.trace"].create(
            {
                "name": "ONE-PRESS",
                "product_id": machinery_product.id,
                "company_id": self.company.id,
            }
        )
        self.assertNotEqual(vehicle.asset_id.kind_code, press.asset_id.kind_code)

        with self.assertRaises(ValidationError):
            press.asset_id.gps_device_id = device

    def test_writing_the_device_side_moves_the_seat(self):
        device = self._device("GPS-SEAT-001")
        first = self.env["product.trace"].create(
            {
                "name": "SEAT-1",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": device.id,
            }
        )
        second = self.env["product.trace"].create(
            {
                "name": "SEAT-2",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
            }
        )

        device.asset_id = second.asset_id

        self.assertFalse(first.asset_id.gps_device_id)
        self.assertEqual(second.asset_id.gps_device_id, device)
        self.assertEqual(device.asset_id, second.asset_id)


class TestRemoteDeviceAssetAction(DeviceDeviceAssetTestBase):
    def test_action_view_tracked_asset_returns_action(self):
        device = self.DeviceDevice.create(
            {
                "name": "Action Test Device",
                "serial_number": "GPS-ACTION-001",
                "identifier": "GPS-ACTION-001",
                "credential_id": False,
                "config_id": self.config.id,
            }
        )

        vehicle = self.env["product.trace"].create(
            {
                "name": "ACTION-VH",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": device.id,
            }
        )

        action = device.action_view_tracked_asset()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "resource.asset.vehicle")
        self.assertEqual(action["res_id"], vehicle.asset_id.id)

    def test_the_two_asset_buttons_do_not_shadow_each_other(self):
        device = self.DeviceDevice.create(
            {
                "name": "Dual Role Device",
                "serial_number": "GPS-DUAL-001",
                "identifier": "GPS-DUAL-001",
                "credential_id": False,
                "config_id": self.config.id,
            }
        )
        device_as_asset = self.env["product.trace"].create(
            {
                "name": "DEVICE-ITSELF",
                "product_id": self.product.id,
                "company_id": self.company.id,
            }
        )
        device.own_asset_id = device_as_asset.asset_id
        tracked = self.env["product.trace"].create(
            {
                "name": "TRACKED-VH",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": device.id,
            }
        )

        self.assertEqual(
            device.action_view_tracked_asset()["res_id"],
            tracked.asset_id.id,
            "Ours opens the asset the device reports for.",
        )
        self.assertEqual(
            device.action_view_own_asset()["res_id"],
            device_as_asset.asset_id.id,
            "The sibling's method must still reach the asset the device is.",
        )

    def test_action_view_tracked_asset_no_asset_returns_false(self):
        device = self.DeviceDevice.create(
            {
                "name": "No Asset Device",
                "serial_number": "GPS-NOASSET",
                "identifier": "GPS-NOASSET",
                "credential_id": False,
                "config_id": self.config.id,
            }
        )

        result = device.action_view_tracked_asset()

        self.assertFalse(result)
