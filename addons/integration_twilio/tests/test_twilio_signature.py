from odoo.tests import BaseCase, tagged

from odoo.addons.integration_twilio.tools.twilio_signature import (
    compute_signature,
    is_signature_valid,
    url_variants,
)

TOKEN = "12345"
URL = "https://mycompany.com/myapp.php?foo=1&bar=2"
PARAMS = {
    "CallSid": "CA1234567890ABCDE",
    "Caller": "+14158675309",
    "Digits": "1234",
    "From": "+14158675309",
    "To": "+18005551212",
}
SIGNATURE = "RSOYDt4T1cUTdK1PDd93/VVr8B8="


@tagged("post_install", "-at_install", "twilio")
class TestTwilioSignature(BaseCase):
    def test_twilio_published_vector(self):
        self.assertEqual(compute_signature(TOKEN, URL, PARAMS.items()), SIGNATURE)
        self.assertTrue(is_signature_valid(TOKEN, [URL], PARAMS.items(), SIGNATURE))

    def test_default_port_either_way(self):
        with_port = "https://mycompany.com:443/myapp.php?foo=1&bar=2"
        self.assertEqual(url_variants(URL), [URL, with_port])
        self.assertEqual(url_variants(with_port), [with_port, URL])
        self.assertEqual(
            url_variants("https://mycompany.com:8443/x"),
            ["https://mycompany.com:8443/x"],
        )
        self.assertTrue(
            is_signature_valid(TOKEN, [with_port], PARAMS.items(), SIGNATURE)
        )

    def test_repeated_parameters_are_all_signed(self):
        params = [("MediaUrl", "b"), ("MediaUrl", "a"), ("Body", "hi")]
        signature = compute_signature(TOKEN, URL, params)
        self.assertEqual(
            signature,
            compute_signature(
                TOKEN, URL, [("Body", "hi"), ("MediaUrl", "a"), ("MediaUrl", "b")]
            ),
        )
        self.assertFalse(
            is_signature_valid(
                TOKEN, [URL], [("Body", "hi"), ("MediaUrl", "a")], signature
            )
        )

    def test_refusals(self):
        self.assertFalse(is_signature_valid(TOKEN, [URL], PARAMS.items(), None))
        self.assertFalse(is_signature_valid("", [URL], PARAMS.items(), SIGNATURE))
        self.assertFalse(is_signature_valid(TOKEN, [URL], PARAMS.items(), "é" * 28))
        self.assertFalse(is_signature_valid("54321", [URL], PARAMS.items(), SIGNATURE))
        tampered = {**PARAMS, "Digits": "9999"}
        self.assertFalse(is_signature_valid(TOKEN, [URL], tampered.items(), SIGNATURE))
