from odoo.tests import HttpCase, tagged

from odoo.addons.delivery_easypost.tests.common import EasypostTestCommon


@tagged("-at_install", "post_install")
class TestDeliveryEasypostTour(HttpCase, EasypostTestCommon):
    def setUp(self):
        with self.patch_easypost_requests():
            super().setUp()

    def _get_client_action_url(self, delivery_carrier_id):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "delivery.action_delivery_carrier_form"
        )
        return f"/odoo/action-{action['id']}/{delivery_carrier_id}"

    def test_carrier_type_selection_field(self):
        product = self.env["product.product"].create(
            {
                "name": "product1",
                "is_storable": True,
            }
        )

        easypost_carrier = self.env["delivery.carrier"].create(
            {
                "name": "EASYPOST Test",
                "delivery_type": "easypost",
                "easypost_test_api_key": "test",
                "easypost_production_api_key": "test",
                "product_id": product.id,
            }
        )

        url = self._get_client_action_url(easypost_carrier.id)

        with self.patch_easypost_requests():
            self.start_tour(
                url, "test_carrier_type_selection_field", login="admin", timeout=180
            )
