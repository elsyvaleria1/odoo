from odoo.tests.common import TransactionCase


class TestResourceKindGpsActions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        profile = cls.env["device.profile"].create(
            {
                "name": "Kind GPS Profile",
                "auth_type": "bearer",
                "auth_token": "kind_gps_token",
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Kind GPS Tracker",
                "serial_number": "GPS-KIND-001",
                "identifier": "GPS-KIND-001",
                "credential_id": False,
                "config_id": profile.id,
            }
        )
        kind = cls.env.ref("base.kind_vehicle")
        model = cls.env["product.product"].create(
            {"name": "Kind GPS Truck", "type": "consu", "asset_kind_id": kind.id}
        )
        resource = cls.env["resource.resource"].create(
            {
                "name": "Kind GPS Truck",
                "kind_id": kind.id,
                "product_id": model.id,
                "gps_device_id": cls.device.id,
            }
        )
        cls.vehicle = cls.env["resource.asset.vehicle"].browse(resource.id)

    def test_the_vehicle_form_validates_with_the_gps_buttons(self):
        self.env.ref("resource_asset_vehicle.fleet_vehicle_view_form")._check_xml()

    def test_a_vehicle_opens_what_its_resource_opens(self):
        for name in ("action_view_gps_device", "action_view_tracking_history"):
            with self.subTest(action=name):
                self.assertEqual(
                    getattr(self.vehicle, name)(),
                    getattr(self.vehicle.resource_id, name)(),
                )
