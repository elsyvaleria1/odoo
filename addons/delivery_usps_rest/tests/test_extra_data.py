from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestUSPSExtraData(TransactionCase):
    def test_invalid_json_reports_configuration_error(self):
        carrier = self.env.ref("delivery_usps_rest.delivery_carrier_usps_domestic")
        for request_type, field_name in (
            ("rate", "usps_extra_data_rate_request"),
            ("shipment", "usps_extra_data_shipment_request"),
            ("payment_token", "usps_extra_data_payment_token_request"),
        ):
            with self.subTest(request_type=request_type):
                carrier[field_name] = '"unfinished":'
                request = {"existing": "preserved"}
                with self.assertRaisesRegex(
                    UserError, "Invalid syntax for USPS extra data"
                ):
                    carrier._usps_add_extra_data_to_request(request, request_type)
                self.assertEqual(request, {"existing": "preserved"})
