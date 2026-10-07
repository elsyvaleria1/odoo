from odoo.tests.common import TransactionCase


class TestResourceKindAssignationLog(TransactionCase):
    """A vehicle runs the assignation log button of the asset form."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        kind = cls.env.ref("resource_asset.kind_vehicle")
        model = cls.env["product.product"].create(
            {"name": "Kind HR Truck", "type": "consu", "asset_kind_id": kind.id}
        )
        resource = cls.env["resource.resource"].create(
            {"name": "Kind HR Truck", "kind_id": kind.id, "product_id": model.id}
        )
        cls.vehicle = cls.env["resource.asset.vehicle"].browse(resource.id)

    def test_the_vehicle_form_validates_with_the_assignation_log_button(self):
        # create() checks only the nodes a view brings; an upgrade rewrites the
        # view and checks the whole form, the asset form's buttons included
        self.env.ref("resource_asset_vehicle.fleet_vehicle_view_form")._check_xml()

    def test_a_vehicle_opens_what_its_resource_opens(self):
        self.assertEqual(
            self.vehicle.action_view_logs_assignation(),
            self.vehicle.resource_id.action_view_logs_assignation(),
        )
