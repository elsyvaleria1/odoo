import base64
import io

from PIL import Image

from odoo.tests import TransactionCase, tagged


def _png_data_uri():
    image = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(image, "PNG")
    return "data:image/png;base64," + base64.b64encode(image.getvalue()).decode()


@tagged("post_install", "-at_install")
class TestHtmlDataImages(TransactionCase):
    def _images_of(self, partner):
        return self.env["ir.attachment"].search(
            [("res_model", "=", "res.partner"), ("res_id", "=", partner.id)]
        )

    def test_create_moves_a_data_uri_image_to_an_attachment(self):
        partner = self.env["res.partner"].create(
            {"name": "Pasted", "comment": f'<p><img src="{_png_data_uri()}"></p>'}
        )
        image = self._images_of(partner)
        self.assertEqual(len(image), 1)
        self.assertNotIn("data:image", partner.comment)
        self.assertIn(f"/web/image/{image.id}?access_token=", partner.comment)
        self.assertEqual(image.mimetype, "image/png")

    def test_write_moves_it_once_per_distinct_image(self):
        partner = self.env["res.partner"].create({"name": "Pasted"})
        uri = _png_data_uri()
        partner.comment = f'<p><img src="{uri}"><img src="{uri}"></p>'
        self.assertEqual(len(self._images_of(partner)), 1)
        self.assertNotIn("data:image", partner.comment)

    def test_html_without_data_uri_is_left_alone(self):
        partner = self.env["res.partner"].create(
            {"name": "Plain", "comment": "<p>data:image is just text here</p>"}
        )
        self.assertFalse(self._images_of(partner))
        self.assertIn("data:image is just text here", partner.comment)
