from odoo.tests.common import TransactionCase


class TestResourceKindMaintenanceOrder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        kind = cls.env.ref("base.kind_vehicle")
        model = cls.env["product.product"].create(
            {
                "name": "Kind Maintenance Truck",
                "type": "consu",
                "asset_kind_id": kind.id,
            }
        )
        resource = cls.env["resource.resource"].create(
            {
                "name": "Kind Maintenance Truck",
                "kind_id": kind.id,
                "product_id": model.id,
            }
        )
        cls.vehicle = cls.env["resource.asset.vehicle"].browse(resource.id)

    def test_the_vehicle_form_validates_with_the_maintenance_order_button(self):
        self.env.ref("resource_asset_vehicle.fleet_vehicle_view_form")._check_xml()

    def test_a_vehicle_opens_what_its_resource_opens(self):
        self.assertEqual(
            self.vehicle.action_create_maintenance_order(),
            self.vehicle.resource_id.action_create_maintenance_order(),
        )
