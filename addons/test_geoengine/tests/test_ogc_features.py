from datetime import datetime, timedelta

from pyproj import Transformer

from odoo import Command
from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.geoengine.models import ogc_features as ogc
from odoo.addons.test_geoengine.models.ogc_features import OgcSite, OgcUnread

ARCH = """<geoengine>
    <field name="name"/><field name="kind"/><field name="seen"/><field name="working"/>
    <field name="owner_id"/><field name="secret"/><field name="position"/>
    <templates><t t-name="info_box"><div/></t></templates>
</geoengine>"""

TO_MERCATOR = Transformer.from_crs(4326, 3857, always_xy=True)


class OgcFixture:
    @classmethod
    def _setup_ogc(cls):
        cls.Site, cls.Unread = (cls.env[OgcSite._name], cls.env[OgcUnread._name])
        group_user = cls.env.ref("base.group_user")
        for model in (OgcSite,):
            cls.env["ir.access"].create(
                {
                    "name": f"{model._name} read",
                    "model_id": cls.env["ir.model"]._get_id(model._name),
                    "group_id": group_user.id,
                    "kind": "permission",
                    "operation": "r",
                    "domain": "[('name', '!=', 'secret site')]",
                }
            )
        fields_of = cls.env["ir.model.fields"]._get
        for model, geo in (
            (OgcSite, "position"),
            (OgcSite, "hidden_position"),
            (OgcUnread, "position"),
        ):
            view = cls.env["ir.ui.view"].create(
                {
                    "name": f"{model._name} map",
                    "model": model._name,
                    "type": "geoengine",
                    "arch": ARCH
                    if model is OgcSite
                    else ARCH.replace(
                        '<field name="kind"/><field name="seen"/><field name="working"/>\n    <field name="owner_id"/><field name="secret"/>',
                        "",
                    ),
                }
            )
            cls.env["geoengine.vector.layer"].create(
                {
                    "name": f"{model._name} {geo}",
                    "view_id": view.id,
                    "geo_field_id": fields_of(model._name, geo).id,
                    "geo_repr": "basic",
                }
            )
        cls.plain = cls.env["res.users"].create(
            {
                "name": "OGC map reader",
                "login": "geoengine_ogc_reader",
                "password": "geoengine_ogc_reader",
                "group_ids": [Command.set([group_user.id])],
            }
        )
        lonlats = [(-107.65 + i * 0.01, 25.1 + i * 0.01) for i in range(5)]
        cls.sites = cls.Site.create(
            [
                {
                    "name": f"site {i}",
                    "kind": "well" if i % 2 else "pump",
                    "seen": f"2026-09-0{i + 1}",
                    "working": bool(i % 2),
                    "owner_id": cls.plain.id if i == 0 else False,
                    "secret": "hush",
                    "position": "POINT({} {})".format(*TO_MERCATOR.transform(lon, lat)),
                }
                for i, (lon, lat) in enumerate(lonlats)
            ]
        )
        cls.lonlats = dict(zip(cls.sites.ids, lonlats, strict=True))
        cls.secret_site = cls.Site.create(
            {"name": "secret site", "position": "POINT(0 0)"}
        )


@tagged("post_install", "-at_install", "geoengine_audit")
class TestOgcFeatures(TransactionCase, OgcFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_ogc()
        cls.env_plain = cls.env(user=cls.plain)
        cls.collection = ogc.find_collection(
            cls.env_plain, "geoengine.test.ogc.site.position"
        )

    def test_a_reader_sees_the_geometries_they_may_read_as_collections(self):
        ids = [c.id for c in ogc.collections(self.env_plain)]
        self.assertIn("geoengine.test.ogc.site.position", ids)
        self.assertNotIn("geoengine.test.ogc.site.hidden_position", ids)
        self.assertNotIn("geoengine.test.ogc.unread.position", ids)
        self.assertIn(
            "geoengine.test.ogc.site.hidden_position",
            [c.id for c in ogc.collections(self.env)],
        )

    def test_properties_are_the_map_view_s_readable_scalar_fields(self):
        self.assertEqual(
            ogc.property_names(self.env_plain, self.collection),
            ["name", "kind", "seen", "working", "owner_id"],
        )

    def test_items_are_crs84_geojson_with_their_properties_in_id_order(self):
        document = ogc.items(self.env_plain, self.collection, "http://x/ogcapi")
        self.assertEqual(document["type"], "FeatureCollection")
        self.assertEqual([f["id"] for f in document["features"]], self.sites.ids)
        first = document["features"][0]
        lon, lat = self.lonlats[first["id"]]
        self.assertEqual(first["geometry"]["type"], "Point")
        self.assertAlmostEqual(first["geometry"]["coordinates"][0], lon, places=7)
        self.assertAlmostEqual(first["geometry"]["coordinates"][1], lat, places=7)
        self.assertEqual(
            first["properties"],
            {
                "name": "site 0",
                "kind": "pump",
                "seen": "2026-09-01",
                "working": False,
                "owner_id": "OGC map reader",
            },
        )
        self.assertIsNone(document["features"][1]["properties"]["owner_id"])
        self.assertEqual(document["numberReturned"], 5)

    def test_record_rules_hide_records_from_items_and_item(self):
        ids = [
            f["id"]
            for f in ogc.items(self.env_plain, self.collection, "http://x")["features"]
        ]
        self.assertNotIn(self.secret_site.id, ids)
        self.assertIsNone(
            ogc.item(self.env_plain, self.collection, self.secret_site.id, "http://x")
        )
        self.assertEqual(
            ogc.item(self.env_plain, self.collection, self.sites[2].id, "http://x")[
                "properties"
            ]["name"],
            "site 2",
        )

    def test_bbox_selects_the_records_inside_it(self):
        bbox = ogc.parse_bbox(self.env, "-107.645,25.0,-107.625,26")
        document = ogc.items(self.env_plain, self.collection, "http://x", bbox=bbox)
        self.assertEqual([f["id"] for f in document["features"]], self.sites[1:3].ids)
        self.assertIn("bbox=", document["links"][0]["href"])

    def test_pages_link_to_their_neighbours(self):
        page = ogc.items(self.env_plain, self.collection, "http://x", limit=2, offset=2)
        self.assertEqual([f["id"] for f in page["features"]], self.sites[2:4].ids)
        rels = {link["rel"]: link["href"] for link in page["links"]}
        self.assertTrue(rels["next"].endswith("limit=2&offset=4"))
        self.assertTrue(rels["prev"].endswith("limit=2&offset=0"))
        last = ogc.items(self.env_plain, self.collection, "http://x", limit=2, offset=4)
        self.assertNotIn("next", {link["rel"] for link in last["links"]})

    def test_the_extent_is_in_crs84(self):
        bbox = ogc.collection_extent(self.env_plain, self.collection)
        lons = [lon for lon, _lat in self.lonlats.values()]
        lats = [lat for _lon, lat in self.lonlats.values()]
        for got, want in zip(
            bbox, (min(lons), min(lats), max(lons), max(lats)), strict=True
        ):
            self.assertAlmostEqual(got, want, places=6)

    def test_malformed_parameters_are_refused(self):
        for raw in ("1,2,3", "a,b,c,d", "10,0,5,1"):
            with self.subTest(bbox=raw), self.assertRaises(ogc.OgcRequestError):
                ogc.parse_bbox(self.env, raw)
        for limit, offset in (("0", None), ("x", None), (None, "-1")):
            with (
                self.subTest(limit=limit, offset=offset),
                self.assertRaises(ogc.OgcRequestError),
            ):
                ogc.parse_page(self.env, limit, offset)
        self.assertEqual(ogc.parse_page(self.env, "999999", None), (ogc.MAX_LIMIT, 0))


@tagged("post_install", "-at_install", "geoengine_audit")
class TestOgcFeaturesHttp(HttpCase, OgcFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_ogc()
        expires = datetime.now() + timedelta(days=1)
        ApiKeys = cls.env["res.users.apikeys"].with_user(cls.plain)
        cls.ogc_key = ApiKeys._generate("ogcapi", "QGIS", expires)
        cls.rpc_key = ApiKeys._generate("rpc", "elsewhere", expires)

    def _get(self, path, key=None):
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        return self.url_open(path, headers=headers, allow_redirects=False)

    def test_the_api_answers_a_key_of_its_scope(self):
        landing = self._get("/ogcapi", self.ogc_key)
        self.assertEqual(landing.status_code, 200)
        self.assertEqual(
            {link["rel"] for link in landing.json()["links"]},
            {"self", "service-desc", "conformance", "data"},
        )
        api = self._get("/ogcapi/api", self.ogc_key)
        self.assertEqual(api.status_code, 200)
        self.assertIn("/collections/{collectionId}/items", api.json()["paths"])
        self.assertIn(
            ogc.CONFORMANCE[0],
            self._get("/ogcapi/conformance", self.ogc_key).json()["conformsTo"],
        )
        collections = self._get("/ogcapi/collections", self.ogc_key).json()[
            "collections"
        ]
        self.assertIn(
            "geoengine.test.ogc.site.position", [c["id"] for c in collections]
        )

    def test_items_are_served_as_geojson(self):
        response = self._get(
            "/ogcapi/collections/geoengine.test.ogc.site.position/items?limit=2",
            self.ogc_key,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["Content-Type"].startswith("application/geo+json")
        )
        body = response.json()
        self.assertEqual(body["numberReturned"], 2)
        self.assertIn("next", {link["rel"] for link in body["links"]})
        feature = self._get(
            f"/ogcapi/collections/geoengine.test.ogc.site.position/items/{self.sites[0].id}",
            self.ogc_key,
        ).json()
        self.assertEqual(feature["properties"]["name"], "site 0")

    def test_unknown_collections_features_and_bad_parameters_are_answered(self):
        self.assertEqual(
            self._get("/ogcapi/collections/no.such.thing", self.ogc_key).status_code,
            404,
        )
        self.assertEqual(
            self._get(
                f"/ogcapi/collections/geoengine.test.ogc.site.position/items/{self.secret_site.id}",
                self.ogc_key,
            ).status_code,
            404,
        )
        bad = self._get(
            "/ogcapi/collections/geoengine.test.ogc.site.position/items?bbox=1,2,3",
            self.ogc_key,
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(json_loads(bad.content)["code"], "InvalidParameterValue")

    def test_no_key_or_a_key_of_another_scope_is_refused(self):
        self.assertEqual(self._get("/ogcapi/collections").status_code, 401)
        self.assertEqual(
            self._get("/ogcapi/collections", self.rpc_key).status_code, 401
        )
