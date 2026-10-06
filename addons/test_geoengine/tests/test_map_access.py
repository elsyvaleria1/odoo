from pyproj import Transformer

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.geoengine.models.base import COUNTRY_EXTENTS
from odoo.addons.test_geoengine.models.map_access import AccessHidden, AccessSite

ARCH = """<geoengine>
    <field name="name"/>
    <field name="position"/>
    <templates><t t-name="info_box"><div><t t-out="record.name"/></div></t></templates>
</geoengine>"""


@tagged("post_install", "-at_install", "geoengine_audit")
class TestMapAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Site, cls.Hidden = (cls.env[AccessSite._name], cls.env[AccessHidden._name])
        cls.env["ir.access"].create(
            {
                "name": "access site read",
                "model_id": cls.env["ir.model"]._get_id(AccessSite._name),
                "group_id": cls.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "r",
            }
        )
        cls.plain = cls.env["res.users"].create(
            {
                "name": "plain map user",
                "login": "geoengine_map_access_plain",
                "group_ids": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )

    def _view(self, model, **values):
        return self.env["ir.ui.view"].create(
            {"name": "map", "model": model, "type": "geoengine", "arch": ARCH} | values
        )

    def test_layers_of_a_model_the_user_cannot_read_are_refused(self):
        view = self._view(AccessHidden._name)
        self.env["geoengine.raster.layer"].create(
            {
                "name": "keyed tiles",
                "view_id": view.id,
                "raster_type": "xyz",
                "url": "https://tiles.example.com/{z}/{x}/{y}.png?key=SECRET",
            }
        )
        with self.assertRaises(AccessError):
            self.Hidden.with_user(self.plain).get_layers()
        with self.assertRaises(AccessError):
            self.Hidden.with_user(self.plain).get_layers(view.id)

    def test_layers_of_a_readable_model_are_served(self):
        view = self._view(AccessSite._name)
        payload = self.Site.with_user(self.plain).get_layers(view.id)
        self.assertEqual(payload["actives"], [])

    def test_the_default_map_is_the_one_the_client_opens(self):
        self._view(AccessSite._name, name="late, low priority", priority=30)
        preferred = self._view(AccessSite._name, name="preferred", priority=1)
        self._view(
            AccessSite._name,
            name="extension",
            inherit_id=preferred.id,
            mode="extension",
            priority=0,
            arch='<field name="name" position="attributes">'
            '<attribute name="string">Site</attribute></field>',
        )
        opened = self.Site.get_views([(False, "geoengine")])["views"]["geoengine"]
        self.assertEqual(opened["id"], preferred.id)
        self.assertEqual(self.Site._get_geo_view(), preferred)

        site_field = self.env["ir.model.fields"]._get(AccessSite._name, "position")
        layer = self.env["geoengine.vector.layer"].create(
            {
                "name": "sites",
                "view_id": self._view(AccessHidden._name).id,
                "geo_field_id": site_field.id,
                "geo_repr": "basic",
            }
        )
        self.assertEqual(layer.model_view_id, preferred)

    def test_a_reference_operand_respects_field_groups(self):
        self.Site.create(
            {
                "name": "inside",
                "position": "POINT(5 5)",
                "zone": "POLYGON((0 0,10 0,10 10,0 10,0 0))",
            }
        )
        operand = {f"{AccessSite._name}.zone": []}
        found = self.Site.search([("position", "geo_within", operand)])
        self.assertEqual(found.mapped("name"), ["inside"])
        with self.assertRaises(AccessError):
            self.Site.with_user(self.plain).search(
                [("position", "geo_within", operand)]
            )

    def test_a_reference_operand_follows_record_rules_and_domain(self):
        self.Site.create(
            [
                {"name": "a", "position": "POINT(5 5)"},
                {"name": "b", "position": "POINT(50 50)"},
            ]
        )
        operand = {f"{AccessSite._name}.position": [("name", "=", "a")]}
        found = self.Site.search([("position", "geo_equal", operand)])
        self.assertEqual(found.mapped("name"), ["a"])
        nothing = {f"{AccessSite._name}.position": [("name", "=", "missing")]}
        self.assertFalse(self.Site.search([("position", "geo_equal", nothing)]))

    def test_an_extent_reprojects_to_its_true_bounds(self):
        extent = COUNTRY_EXTENTS["MX"]
        served = self.Site._extent_in_projection(extent, "EPSG:32614")
        min_x, min_y, max_x, max_y = (float(v) for v in served.split(","))
        corners = [float(v) for v in extent.split(",")]
        true_min_x, true_min_y, true_max_x, true_max_y = Transformer.from_crs(
            3857, 32614, always_xy=True
        ).transform_bounds(*corners, densify_pts=200)
        slack = 0.001 * max(true_max_x - true_min_x, true_max_y - true_min_y)
        self.assertLessEqual(min_x, true_min_x + slack)
        self.assertLessEqual(min_y, true_min_y + slack)
        self.assertGreaterEqual(max_x, true_max_x - slack)
        self.assertGreaterEqual(max_y, true_max_y - slack)

    def test_a_layer_domain_reaches_the_map_as_the_server_evaluates_it(self):
        view = self._view(AccessSite._name)
        field = self.env["ir.model.fields"]._get(AccessSite._name, "position")
        layer = self.env["geoengine.vector.layer"].create(
            {
                "name": "mine",
                "view_id": view.id,
                "geo_field_id": field.id,
                "geo_repr": "basic",
                "model_domain": "[('create_uid', '=', user.id),"
                " ('id', 'in', '{ACTIVE_IDS}')]",
            }
        )
        [row] = self.Site.with_user(self.plain).get_layers(view.id)["actives"]
        self.assertEqual(
            [list(term) for term in row["domain"]],
            [["create_uid", "=", self.plain.id], ["id", "in", "{ACTIVE_IDS}"]],
        )
        self.env.cr.execute(
            "UPDATE geoengine_vector_layer SET model_domain = %s WHERE id = %s",
            ("[('name', '=', undefined_name)]", layer.id),
        )
        layer.invalidate_recordset()
        [row] = self.Site.get_layers(view.id)["actives"]
        self.assertIsNone(row["domain"])

    def test_a_plain_user_reads_the_map_view_a_layer_draws_from(self):
        view = self._view(AccessSite._name)
        layer = self.env["geoengine.vector.layer"].create(
            {
                "name": "sites",
                "view_id": view.id,
                "model_id": self.env["ir.model"]._get_id(AccessSite._name),
                "geo_field_id": self.env["ir.model.fields"]
                ._get(AccessSite._name, "position")
                .id,
                "geo_repr": "basic",
            }
        )
        self.env.invalidate_all()
        self.assertEqual(
            layer.with_user(self.plain).model_view_id.id,
            self.env["ir.ui.view"].default_view(AccessSite._name, "geoengine"),
        )
