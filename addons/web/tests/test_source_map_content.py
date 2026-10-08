from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install", "web_assets")
class TestSourceMapContent(HttpCase):
    """A generated asset is a public attachment; its source map, which carries
    every bundled source, is the server's and its administrators' alone unless
    the maps are linked."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.map = cls.env["ir.attachment"].create(
            {
                "name": "probe.esm.js.map",
                "url": "/web/assets/esm/probe/probe.esm.js.map",
                "public": True,
                "res_model": "ir.ui.view",
                "res_id": 0,
                "mimetype": "application/json",
                "raw": b'{"sourcesContent": ["// the source"]}',
            }
        )
        new_test_user(cls.env, "map.employee", password="map.employee.pass")

    def _status(self, url):
        return self.url_open(url).status_code

    def test_a_visitor_gets_no_source_map(self):
        self.assertEqual(self._status(f"/web/content/{self.map.id}"), 404)
        for url in (
            f"/web/image/{self.map.id}",
            f"/web/image/ir.attachment/{self.map.id}/raw",
            f"/web/image?model=ir.attachment&id={self.map.id}&field=raw",
        ):
            # a refused image answers its placeholder: what matters is the body
            self.assertNotIn(b"the source", self.url_open(url).content, url)
        self.assertEqual(
            self._status(f"/web/content?model=ir.attachment&id={self.map.id}"), 404
        )
        self.assertEqual(self._status("/web/assets/any/web.assets_web.min.js.map"), 404)

    def test_an_employee_gets_no_source_map(self):
        self.authenticate("map.employee", "map.employee.pass")
        self.assertEqual(self._status(f"/web/content/{self.map.id}"), 404)
        self.assertNotIn(
            b"the source", self.url_open(f"/web/image/{self.map.id}").content
        )

    def test_an_employee_reads_no_source_map_over_rpc(self):
        employee = self.env["res.users"].search([("login", "=", "map.employee")])
        Attachment = self.env["ir.attachment"].with_user(employee)
        self.assertFalse(Attachment.search([("id", "=", self.map.id)]))
        with self.assertRaises(AccessError):
            Attachment.browse(self.map.id).read(["raw"])

    def test_an_administrator_gets_the_source_map(self):
        self.authenticate("admin", "admin")
        self.assertEqual(self._status(f"/web/content/{self.map.id}"), 200)
        self.assertIn(
            b"the source", self.url_open(f"/web/content/{self.map.id}").content
        )

    def test_linked_maps_are_everyones(self):
        self.env["ir.config_parameter"].set_param("web.esbuild.source_maps", "linked")
        self.assertEqual(self._status(f"/web/content/{self.map.id}"), 200)
