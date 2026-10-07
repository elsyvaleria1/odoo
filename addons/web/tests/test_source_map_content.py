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
        self.assertEqual(
            self._status(f"/web/content?model=ir.attachment&id={self.map.id}"), 404
        )
        self.assertEqual(self._status("/web/assets/any/web.assets_web.min.js.map"), 404)

    def test_an_employee_gets_no_source_map(self):
        self.authenticate("map.employee", "map.employee.pass")
        self.assertEqual(self._status(f"/web/content/{self.map.id}"), 404)

    def test_an_administrator_gets_the_source_map(self):
        self.authenticate("admin", "admin")
        self.assertEqual(self._status(f"/web/content/{self.map.id}"), 200)

    def test_linked_maps_are_everyones(self):
        self.env["ir.config_parameter"].set_param("web.esbuild.source_maps", "linked")
        self.assertEqual(self._status(f"/web/content/{self.map.id}"), 200)
