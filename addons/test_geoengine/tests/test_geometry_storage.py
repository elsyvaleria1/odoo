import shapely
from pyproj import Geod
from shapely.geometry import Point

from odoo.exceptions import ValidationError
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.geoengine.models.fields import reproject
from odoo.addons.test_geoengine.models.geometry_storage import StorageMixin, StorageSite

MEXICO_CITY = Point(-99.1332, 19.4326)


@tagged("post_install", "-at_install", "geoengine_audit")
class TestGeometryStorage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Site, _mixin = (cls.env[StorageSite._name], cls.env[StorageMixin._name])

    def _stored(self, record, column):
        record.flush_recordset()
        self.env.cr.execute(
            f"SELECT ST_SRID({column}), ST_X({column}), ST_Y({column}), "
            f"ST_NDims({column}) FROM geoengine_test_storage_site WHERE id = %s",
            (record.id,),
        )
        return self.env.cr.fetchone()

    def _assert_mexico_city_in_mercator(self, record):
        expected = reproject(MEXICO_CITY, 4326, 3857)
        srid, x, y, _dims = self._stored(record, "mercator")
        self.assertEqual(srid, 3857)
        self.assertAlmostEqual(x, expected.x, delta=0.01)
        self.assertAlmostEqual(y, expected.y, delta=0.01)

    def test_ewkb_declaring_another_srid_is_reprojected(self):
        ewkb = shapely.to_wkb(
            shapely.set_srid(MEXICO_CITY, 4326), hex=True, include_srid=True
        )
        self._assert_mexico_city_in_mercator(self.Site.create({"mercator": ewkb}))

    def test_shapely_geometry_carrying_its_srid_is_reprojected(self):
        geometry = shapely.set_srid(MEXICO_CITY, 4326)
        self._assert_mexico_city_in_mercator(self.Site.create({"mercator": geometry}))

    def test_a_record_geometry_keeps_its_place_in_another_srid(self):
        source = self.Site.create({"wgs84": "SRID=4326;POINT(-99.1332 19.4326)"})
        copy = self.Site.create({"mercator": source.wgs84})
        self._assert_mexico_city_in_mercator(copy)

    def test_a_malformed_srid_prefix_is_refused(self):
        with self.assertRaises(ValidationError):
            self.Site.create({"mercator": "SRID=abc;POINT(1 2)"})

    def test_z_is_dropped_for_a_2d_column(self):
        site = self.Site.create({"wgs84": "POINT Z (-99.1 19.4 2240)"})
        self.assertEqual(self._stored(site, "wgs84")[3], 2)

    def test_z_is_added_for_a_3d_column(self):
        site = self.Site.create({"elevated": "POINT (-99.1 19.4)"})
        self.assertEqual(self._stored(site, "elevated")[3], 3)
        self.assertEqual(site.elevated.z, 0)

    def test_the_cache_holds_what_the_column_returns(self):
        site = self.Site.create({"mercator": "POINT(100 200)"})
        cached = site._fields["mercator"].convert_to_cache("POINT(100 200)", site)
        site.flush_recordset()
        site.invalidate_recordset()
        self.env.cr.execute(
            "SELECT mercator FROM geoengine_test_storage_site WHERE id = %s",
            (site.id,),
        )
        self.assertEqual(cached.upper(), self.env.cr.fetchone()[0].upper())

    def test_an_srid_migration_keeps_a_3d_column_and_its_data(self):
        field = self.Site._fields["elevated"]
        self.env.cr.execute(
            "ALTER TABLE geoengine_test_storage_site ALTER COLUMN elevated "
            "TYPE geometry(POINTZ, 3857) USING ST_Transform(elevated, 3857)"
        )
        self.env.cr.execute(
            "INSERT INTO geoengine_test_storage_site (elevated) VALUES "
            "(ST_Transform(ST_SetSRID(ST_MakePoint(-99.1332, 19.4326, 2240), 4326), 3857))"
            " RETURNING id"
        )
        [row_id] = self.env.cr.fetchone()

        with self.assertLogs("odoo.schema", "INFO"):
            field.update_db_column(self.Site, {"udt_name": "geometry"})

        self.env.cr.execute(
            "SELECT srid, type, coord_dimension FROM geometry_columns "
            "WHERE f_table_name = 'geoengine_test_storage_site' "
            "AND f_geometry_column = 'elevated'"
        )
        self.assertEqual(self.env.cr.fetchone(), (4326, "POINT", 3))
        self.env.cr.execute(
            "SELECT ST_X(elevated), ST_Y(elevated), ST_Z(elevated) "
            "FROM geoengine_test_storage_site WHERE id = %s",
            (row_id,),
        )
        x, y, z = self.env.cr.fetchone()
        self.assertAlmostEqual(x, -99.1332, delta=1e-6)
        self.assertAlmostEqual(y, 19.4326, delta=1e-6)
        self.assertAlmostEqual(z, 2240, delta=1e-6)

    def test_spatial_index_actions_target_only_tables(self):
        settings = self.env["res.config.settings"].create({})
        targets = settings._spatial_index_targets()
        self.assertIn(("geoengine_test_storage_site", "mercator"), targets)
        self.assertNotIn(("geoengine_test_storage_mixin", "spot"), targets)

        message = settings.action_create_missing_spatial_indexes()["params"]["message"]
        self.assertNotIn("failed", message)

    def test_aggregates_are_geojson_in_a_client_renderable_crs(self):
        self.Site.create(
            [
                {"name": "a", "lambert": "SRID=4326;POINT(2.35 48.85)"},
                {"name": "a", "lambert": "SRID=4326;POINT(5.37 43.30)"},
            ]
        )
        [(extent, centroid)] = self.Site._read_group(
            [("name", "=", "a")], [], ["lambert:geo_extent", "lambert:geo_centroid"]
        )
        extent = json_loads(extent)
        self.assertEqual(extent["crs"]["properties"]["name"], "EPSG:4326")
        box = shapely.geometry.shape(extent)
        for lon, lat in ((2.35, 48.85), (5.37, 43.30)):
            self.assertTrue(box.buffer(1e-6).contains(Point(lon, lat)), (lon, lat))
        self.assertLess(box.area, 25)
        self.assertEqual(json_loads(centroid)["type"], "Point")

    def test_an_empty_group_aggregates_to_false(self):
        [(extent,)] = self.Site._read_group(
            [("id", "=", -1)], [], ["mercator:geo_extent"]
        )
        self.assertIs(extent, False)

    def test_a_distance_in_metres_finds_points_near_its_edge_in_any_crs(self):
        geod = Geod(ellps="WGS84")
        site_names = []
        for azimuth in (0, 90, 180, 270):
            lon, lat, _ = geod.fwd(MEXICO_CITY.x, MEXICO_CITY.y, azimuth, 495_000)
            name = f"at {azimuth}"
            self.Site.create({"name": name, "utm": f"SRID=4326;POINT({lon} {lat})"})
            site_names.append(name)
        lon, lat, _ = geod.fwd(MEXICO_CITY.x, MEXICO_CITY.y, 180, 505_000)
        self.Site.create({"name": "beyond", "utm": f"SRID=4326;POINT({lon} {lat})"})
        found = self.Site.search(
            [
                (
                    "utm",
                    "geo_dwithin",
                    {
                        "geometry": "SRID=4326;POINT(-99.1332 19.4326)",
                        "distance": 500_000,
                        "unit": "m",
                    },
                )
            ]
        )
        self.assertEqual(sorted(found.mapped("name")), sorted(site_names))
