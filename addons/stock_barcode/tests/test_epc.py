from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestEpcEncoder(HttpCase):
    def test_get_epc_sgtin(self):

        expected_responses = {
            ("09521141123454", False): {
                "000000000000": "3036451fd40c0e4000000000",
                "000000000001": "3036451fd40c0e4000000001",
                "009876543210": "3036451fd40c0e424cb016ea",
                "274877906943": "3036451fd40c0e7fffffffff",
                "274877906944": "An error occurred with field 'serial_integer': An error occurred with method '_encode_integer': Value 274877906944 cannot be represented with 38 bits",
            },
            (
                "2349",
                True,
            ): {
                "Y00050": "3634000000003aacb060c1ab0000000000000000000000000000",
                "Z00050": "3634000000003aad3060c1ab0000000000000000000000000000",
                "!/%&+-*": "3634000000003a90af4a995ad540000000000000000000000000",
                "!/%&+-*$@@": "An error occurred with field 'serial_string': An error occurred with method '_encode_string': Value to encode contains invalid character(s): `$`, `@`",
                "!/%&+-*\\$$$$$####@ @@@@": "An error occurred with field 'serial_string': An error occurred with method '_encode_string': Value to encode contains invalid character(s): `\\`, `$`, `#`, `@`, ` `",
                "ThisIsWayTooLooooooooong": "An error occurred with field 'serial_string': An error occurred with method '_encode_string': Value 2069674681595411174842736530632876419756036725000752819815 cannot be represented with 140 bits",
            },
        }

        self.authenticate("admin", "admin")

        for gtin_alpha, expected_epc in expected_responses.items():
            gtin, alphanumeric_tracking = gtin_alpha
            tracking_number_list = list(expected_epc.keys())

            payload = json_dumps(
                {
                    "params": {
                        "gtin": gtin,
                        "tracking_number_list": tracking_number_list,
                        "filter_value": 1,
                        "company_prefix_length": 7,
                        "alphanumeric_tracking": alphanumeric_tracking,
                    },
                }
            )
            response = self.url_open(
                "/stock_barcode/get_epc_sgtin",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            received_epc = response.json()[
                "result"
            ]
            self.assertDictEqual(expected_epc, received_epc)

    def test_get_epc_takes_the_filter_value(self):
        self.authenticate("admin", "admin")
        response = self.url_open(
            "/stock_barcode/get_epc",
            data=json_dumps(
                {
                    "params": {
                        "scheme_name": "sgtin-96",
                        "element_string_list": ["(01) 09521141123454 (21) 1"],
                        "company_prefix_length": 7,
                        "filter_value": 1,
                    },
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(
            response.json().get("result"),
            {"(01) 09521141123454 (21) 1": "3036451fd40c0e4000000001"},
            response.text,
        )
