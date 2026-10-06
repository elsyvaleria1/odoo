import base64
from types import SimpleNamespace

from odoo.tests.common import TransactionCase, tagged

PNG_1PX = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    b"AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@tagged("post_install", "-at_install")
class TestLookupImage(TransactionCase):
    def _fake_response(self, payload):
        return SimpleNamespace(content=payload)

    def test_set_lookup_image_main_then_extra(self):
        template = self.env["product.template"].create({"name": "Lookup Product"})
        product = template.product_variant_id

        result = template._set_lookup_image(product, self._fake_response(PNG_1PX))
        self.assertIs(result, True, "First image fills the main image")
        self.assertTrue(product.image_1920)
        self.assertFalse(template.product_template_image_ids)

        result = template._set_lookup_image(product, self._fake_response(PNG_1PX))
        self.assertIsNot(result, True)
        self.assertEqual(len(template.product_template_image_ids), 1)
        self.assertEqual(template.product_template_image_ids.name, product.name)
        self.assertTrue(template.product_template_image_ids.image_1920)
