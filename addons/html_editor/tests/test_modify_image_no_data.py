import odoo.tests
from odoo.tests.common import HttpCase, new_test_user
from odoo.tools.json import scriptsafe as json_safe


@odoo.tests.tagged("-at_install", "post_install")
class TestModifyImageNoData(HttpCase):
    def setUp(self):
        super().setUp()
        self.authenticate("admin", "admin")
        self.pixel = "R0lGODlhAQABAIAAAP///wAAACwAAAAAAQABAAACAkQBADs="

    def test_modify_image_no_data(self):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "test_image.gif",
                "datas": self.pixel,
                "res_model": "ir.ui.view",
                "res_id": 0,
            }
        )

        response = self.url_open(
            f"/html_editor/modify_image/{attachment.id}",
            headers={"Content-Type": "application/json"},
            data=json_safe.dumps(
                {
                    "params": {
                        "res_model": "ir.ui.view",
                        "res_id": 0,
                        "name": "modified_image.gif",
                    }
                }
            ),
        )
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertNotIn("error", response_data)
        self.assertIn("result", response_data)

        modified_attachment = self.env["ir.attachment"].search(
            [
                ("name", "=", "modified_image.gif"),
                ("original_id", "=", attachment.id),
            ]
        )
        self.assertEqual(len(modified_attachment), 1)

    def test_a_shaped_image_of_an_author_who_cannot_write_views_keeps_its_src(self):
        author = new_test_user(
            self.env,
            login="modify_image_author",
            groups="base.group_user,base.group_partner_manager",
        )
        self.assertFalse(self.env["ir.ui.view"].with_user(author).has_access("write"))
        partner = self.env["res.partner"].create({"name": "Image owner"})
        original = (
            self.env["ir.attachment"]
            .with_user(author)
            .create(
                {
                    "name": "pixel.gif",
                    "datas": self.pixel,
                    "res_model": "res.partner",
                    "res_id": partner.id,
                }
            )
        )
        self.authenticate(author.login, author.login)
        response = self.url_open(
            f"/html_editor/modify_image/{original.id}",
            headers={"Content-Type": "application/json"},
            data=json_safe.dumps(
                {
                    "params": {
                        "res_model": "res.partner",
                        "res_id": partner.id,
                        "name": "shaped.svg",
                        "data": self.pixel,
                        "shape": {"id": "html_builder/geometric/geo_diamond"},
                    }
                }
            ),
        )
        src = response.json()["result"]
        self.assertTrue(src.startswith("/web/image/"), src)
        served = self.url_open(src)
        self.assertEqual(served.status_code, 200)
        self.assertTrue(served.headers["Content-Type"].startswith("image/svg+xml"))
