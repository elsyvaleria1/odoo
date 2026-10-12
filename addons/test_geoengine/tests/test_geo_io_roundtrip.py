import base64
import io
import sqlite3
import zipfile

import shapefile
from pyproj import CRS
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.wkb import loads as wkb_loads

from odoo.exceptions import UserError
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.geoengine.wizards import (
    wizard_base_export_geodata,
    wizard_base_import_geodata,
)
from odoo.addons.geoengine.wizards.wizard_base_import_geodata import _gpb_to_wkb
from odoo.addons.test_geoengine.models.geo_io_roundtrip import IoParcel

WGS84_PRJ = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,'
    'AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,'
    'AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,'
    'AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]'
)


@tagged("post_install", "-at_install", "geoengine_audit")
class TestGeoJsonRoundTrip(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Parcel = cls.env[IoParcel._name]
        cls.model_id = cls.env["ir.model"]._get_id(cls.Parcel._name)
        cls.geo_field_id = (
            cls.env["ir.model.fields"]._get(cls.Parcel._name, "boundary").id
        )
        cls.name_field_id = cls.env["ir.model.fields"]._get(cls.Parcel._name, "name").id
        cls.parcels = cls.Parcel.create(
            [
                {
                    "name": "North field",
                    "code": "N1",
                    "area": 12.5,
                    "boundary": (
                        "SRID=4326;POLYGON((-99.20 19.40,-99.10 19.40,"
                        "-99.10 19.50,-99.20 19.50,-99.20 19.40))"
                    ),
                },
                {
                    "name": "South field",
                    "code": "S1",
                    "area": 7.25,
                    "boundary": (
                        "SRID=4326;POLYGON((-99.20 19.20,-99.10 19.20,"
                        "-99.10 19.30,-99.20 19.30,-99.20 19.20))"
                    ),
                },
            ]
        )

    def _export(self, **overrides):
        vals = {
            "model_id": self.model_id,
            "geo_field_id": self.geo_field_id,
            "output_srid": "4326",
        }
        vals.update(overrides)
        wizard = self.env["wizard.base.export.geodata"].create(vals)
        wizard.action_export()
        return wizard, json_loads(base64.b64decode(wizard.output_file).decode("utf-8"))

    def test_an_export_over_the_byte_cap_is_refused(self):
        self.patch(wizard_base_export_geodata, "MAX_EXPORT_BYTES", 32)

        with self.assertRaises(UserError) as caught:
            self._export()

        self.assertIn("MB limit", str(caught.exception))

    def test_the_export_byte_cap_matches_the_import_one(self):
        self.assertEqual(
            wizard_base_export_geodata.MAX_EXPORT_BYTES,
            wizard_base_import_geodata.MAX_IMPORT_BYTES,
            "the import path refuses at 64 MB what the export path would "
            "otherwise build, base64-encode and push through the ORM",
        )

    def _import(self, payload, **overrides):
        vals = {
            "model_id": self.model_id,
            "geo_field_id": self.geo_field_id,
            "file_data": base64.b64encode(json_dumps_bytes(payload)),
            "file_name": "parcels.geojson",
        }
        vals.update(overrides)
        wizard = self.env["wizard.base.import.geodata"].create(vals)
        wizard.action_import()
        return wizard

    def test_export_writes_a_feature_collection(self):
        _wizard, doc = self._export()
        self.assertEqual(doc["type"], "FeatureCollection")
        self.assertEqual(len(doc["features"]), 2)
        names = sorted(f["properties"].get("id") for f in doc["features"])
        self.assertEqual(names, sorted(self.parcels.ids))
        self.assertEqual(doc["features"][0]["geometry"]["type"], "Polygon")

    def test_export_reprojects_rather_than_relabelling(self):
        _wizard, doc = self._export(output_srid="3857")
        x, y = doc["features"][0]["geometry"]["coordinates"][0][0]
        self.assertGreater(
            abs(x), 180, f"coordinates still look like degrees: {(x, y)}"
        )
        self.assertEqual(doc["crs"]["properties"]["name"], "EPSG:3857")

    def test_export_carries_the_requested_properties(self):
        field_ids = [
            self.env["ir.model.fields"]._get(self.Parcel._name, name).id
            for name in ("name", "code", "area")
        ]
        _wizard, doc = self._export(property_field_ids=[(6, 0, field_ids)])
        props = doc["features"][0]["properties"]
        self.assertIn("name", props)
        self.assertIn("code", props)
        self.assertEqual(props["area"], 12.5)

    def test_export_honours_the_filter(self):
        _wizard, doc = self._export(domain="[('code', '=', 'N1')]")
        self.assertEqual(len(doc["features"]), 1)

    def test_import_creates_records_with_geometry(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-99.30, 19.60],
                                [-99.25, 19.60],
                                [-99.25, 19.65],
                                [-99.30, 19.65],
                                [-99.30, 19.60],
                            ]
                        ],
                    },
                    "properties": {"label": "Imported"},
                }
            ],
        }
        before = self.Parcel.search_count([])
        wizard = self._import(payload)
        self.env.flush_all()
        self.assertEqual(wizard.imported_count, 1)
        self.assertEqual(self.Parcel.search_count([]), before + 1)
        created = self.Parcel.search([], order="id desc", limit=1)
        self.assertTrue(created.boundary, "the imported record has no geometry")
        self.assertAlmostEqual(created.boundary.bounds[0], -99.30, places=4)

    def test_import_honours_the_file_crs(self):
        payload = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "EPSG:3857"}},
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-11045000, 2210000],
                                [-11040000, 2210000],
                                [-11040000, 2215000],
                                [-11045000, 2215000],
                                [-11045000, 2210000],
                            ]
                        ],
                    },
                    "properties": {},
                }
            ],
        }
        self._import(payload)
        self.env.flush_all()
        created = self.Parcel.search([], order="id desc", limit=1)
        minx, miny, _maxx, _maxy = created.boundary.bounds
        self.assertTrue(
            -180 <= minx <= 180 and -90 <= miny <= 90,
            f"Web-Mercator metres stored as degrees: {created.boundary.bounds}",
        )
        self.assertAlmostEqual(minx, -99.22, places=1)

    def test_import_maps_properties_onto_fields(self):
        mapping = self.env["wizard.base.import.geodata.mapping"]
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                    },
                    "properties": {"parcel_code": "X9"},
                }
            ],
        }
        wizard = self.env["wizard.base.import.geodata"].create(
            {
                "model_id": self.model_id,
                "geo_field_id": self.geo_field_id,
                "file_data": base64.b64encode(json_dumps_bytes(payload)),
            }
        )
        code_field = self.env["ir.model.fields"]._get(self.Parcel._name, "code")
        mapping.create(
            {
                "wizard_id": wizard.id,
                "property_name": "parcel_code",
                "field_id": code_field.id,
            }
        )
        wizard.action_import()
        self.env.flush_all()
        self.assertTrue(self.Parcel.search([("code", "=", "X9")]))

    def test_import_skips_the_broken_feature_and_keeps_the_rest(self):
        good = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
            },
            "properties": {},
        }
        broken = {"type": "Feature", "geometry": {"type": "Polygon"}, "properties": {}}
        wizard = self._import(
            {"type": "FeatureCollection", "features": [good, broken, good]},
            skip_invalid=True,
        )
        self.assertEqual(wizard.imported_count, 2)

    def test_import_without_a_geometry_field_is_refused(self):
        with self.assertRaises(UserError):
            self._import(
                {"type": "FeatureCollection", "features": []}, geo_field_id=False
            )

    def test_a_many2one_property_round_trips_by_name(self):
        owner = self.env["res.partner"].create({"name": "Round Trip Owner"})
        self.parcels[0].owner_id = owner
        owner_field = self.env["ir.model.fields"]._get(self.Parcel._name, "owner_id")
        _wizard, doc = self._export(
            domain="[('code', '=', 'N1')]",
            property_field_ids=[(6, 0, [owner_field.id])],
        )
        self.assertEqual(
            doc["features"][0]["properties"]["owner_id"], owner.display_name
        )
        wizard = self._import(
            doc,
            mapping_lines=[
                (0, 0, {"property_name": "owner_id", "field_id": owner_field.id})
            ],
        )
        self.env.flush_all()
        self.assertEqual(wizard.imported_count, 1)
        self.assertEqual(
            self.Parcel.search([], order="id desc", limit=1).owner_id, owner
        )

    def test_a_many2one_property_with_no_match_is_reported(self):
        owner_field = self.env["ir.model.fields"]._get(self.Parcel._name, "owner_id")
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                    },
                    "properties": {"owner_id": "Nobody Of That Name 3f9a"},
                }
            ],
        }
        with self.assertRaises(UserError) as ctx:
            self._import(
                payload,
                skip_invalid=False,
                mapping_lines=[
                    (0, 0, {"property_name": "owner_id", "field_id": owner_field.id})
                ],
            )
        self.assertIn("Nobody Of That Name", str(ctx.exception))

    def test_a_parcel_survives_export_and_reimport(self):
        for srid in ("4326", "3857"):
            with self.subTest(output_srid=srid):
                original = self.parcels[0].boundary
                _wizard, doc = self._export(
                    output_srid=srid, domain="[('code', '=', 'N1')]"
                )
                before = self.Parcel.search_count([])
                self._import(doc)
                self.env.flush_all()
                self.assertEqual(self.Parcel.search_count([]), before + 1)
                reimported = self.Parcel.search([], order="id desc", limit=1).boundary
                self.assertTrue(
                    original.equals_exact(reimported, 1e-6),
                    f"a round trip through EPSG:{srid} moved the parcel:\n"
                    f"  before {original.bounds}\n  after  {reimported.bounds}",
                )


@tagged("post_install", "-at_install", "geoengine_audit")
class TestShapefileRoundTrip(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Parcel = cls.env[IoParcel._name]
        cls.model_id = cls.env["ir.model"]._get_id(cls.Parcel._name)
        cls.geo_field_id = (
            cls.env["ir.model.fields"]._get(cls.Parcel._name, "boundary").id
        )
        cls.parcels = cls.Parcel.create(
            [
                {
                    "name": "North field",
                    "code": "N1",
                    "area": 12.5,
                    "boundary": (
                        "SRID=4326;POLYGON((-99.20 19.40,-99.10 19.40,"
                        "-99.10 19.50,-99.20 19.50,-99.20 19.40))"
                    ),
                },
                {
                    "name": "South field",
                    "code": "S1",
                    "area": 7.25,
                    "boundary": (
                        "SRID=4326;POLYGON((-99.20 19.20,-99.10 19.20,"
                        "-99.10 19.30,-99.20 19.30,-99.20 19.20))"
                    ),
                },
            ]
        )
        cls.donut = cls.Parcel.create(
            {
                "name": "Donut field",
                "code": "D1",
                "area": 3.0,
                "boundary": (
                    "SRID=4326;POLYGON("
                    "(-99.40 19.60,-99.30 19.60,-99.30 19.70,-99.40 19.70,-99.40 19.60),"
                    "(-99.38 19.62,-99.36 19.62,-99.36 19.64,-99.38 19.64,-99.38 19.62))"
                ),
            }
        )

    def _export(self, **overrides):
        vals = {
            "model_id": self.model_id,
            "geo_field_id": self.geo_field_id,
            "output_format": "shapefile",
            "output_srid": "4326",
        }
        vals.update(overrides)
        wizard = self.env["wizard.base.export.geodata"].create(vals)
        wizard.action_export()
        archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(wizard.output_file)))
        return wizard, archive

    def _read_records(self, archive):
        reader = shapefile.Reader(
            shp=io.BytesIO(archive.read("export.shp")),
            shx=io.BytesIO(archive.read("export.shx")),
            dbf=io.BytesIO(archive.read("export.dbf")),
        )
        with reader:
            return list(reader.shapeRecords())

    def _import(self, archive_bytes, **overrides):
        vals = {
            "model_id": self.model_id,
            "geo_field_id": self.geo_field_id,
            "file_data": base64.b64encode(archive_bytes),
            "file_name": "parcels.zip",
        }
        vals.update(overrides)
        wizard = self.env["wizard.base.import.geodata"].create(vals)
        wizard.action_import()
        return wizard

    def _prepare_shapefile_zip(self, polygons, prj_wkt=None):
        shp_buf, shx_buf, dbf_buf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        writer = shapefile.Writer(
            shp=shp_buf, shx=shx_buf, dbf=dbf_buf, shapeType=shapefile.POLYGON
        )
        writer.field("label", "C", size=50)
        for i, poly in enumerate(polygons):
            oriented = orient(poly, sign=-1.0)
            parts = [list(oriented.exterior.coords)]
            parts.extend(list(ring.coords) for ring in oriented.interiors)
            writer.poly(parts)
            writer.record(label=f"p{i}")
        writer.close()

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as archive:
            archive.writestr("t.shp", shp_buf.getvalue())
            archive.writestr("t.shx", shx_buf.getvalue())
            archive.writestr("t.dbf", dbf_buf.getvalue())
            if prj_wkt:
                archive.writestr("t.prj", prj_wkt)
        return zip_buf.getvalue()

    def test_a_shapefile_without_prj_says_the_crs_was_assumed(self):
        square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        wizard = self.env["wizard.base.import.geodata"].create(
            {
                "model_id": self.model_id,
                "geo_field_id": self.geo_field_id,
                "file_data": base64.b64encode(self._prepare_shapefile_zip([square])),
                "file_name": "noprj.zip",
            }
        )
        wizard._onchange_file_data()
        self.assertIn("assumed", wizard.detected_crs)
        action = wizard.action_import()
        self.assertEqual(action["params"]["type"], "warning")
        self.assertIn("assumed", action["params"]["message"])

    def test_a_shapefile_with_prj_names_its_crs(self):
        square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        wizard = self.env["wizard.base.import.geodata"].create(
            {
                "model_id": self.model_id,
                "geo_field_id": self.geo_field_id,
                "file_data": base64.b64encode(
                    self._prepare_shapefile_zip([square], prj_wkt=WGS84_PRJ)
                ),
                "file_name": "prj.zip",
            }
        )
        wizard._onchange_file_data()
        self.assertEqual(wizard.detected_crs, "EPSG:4326")
        self.assertEqual(wizard.action_import()["params"]["type"], "success")

    def test_export_writes_shp_shx_dbf_prj(self):
        _wizard, archive = self._export()
        self.assertEqual(
            set(archive.namelist()),
            {"export.shp", "export.shx", "export.dbf", "export.prj"},
        )

    def test_export_writes_one_record_per_parcel(self):
        _wizard, archive = self._export()
        records = self._read_records(archive)
        self.assertEqual(len(records), 3)
        self.assertEqual({r.shape.shapeTypeName for r in records}, {"POLYGON"})

    def test_export_prj_states_the_output_srid(self):
        _wizard, archive = self._export(output_srid="3857")
        epsg = CRS.from_wkt(archive.read("export.prj").decode("utf-8")).to_epsg()
        self.assertEqual(epsg, 3857)

    def test_export_reprojects_rather_than_relabelling(self):
        _wizard, archive = self._export(output_srid="3857")
        records = self._read_records(archive)
        x, _y = records[0].shape.points[0]
        self.assertGreater(abs(x), 180, f"coordinates still look like degrees: {x}")

    def test_export_carries_the_requested_properties(self):
        field_ids = [
            self.env["ir.model.fields"]._get(self.Parcel._name, name).id
            for name in ("name", "code", "area")
        ]
        _wizard, archive = self._export(property_field_ids=[(6, 0, field_ids)])
        records = self._read_records(archive)
        field_names = self._dbf_field_names(archive)
        self.assertIn("name", field_names)
        self.assertIn("code", field_names)
        self.assertIn("area", field_names)
        self.assertTrue(any(r.record.as_dict().get("code") == "N1" for r in records))

    def _dbf_field_names(self, archive):
        reader = shapefile.Reader(
            shp=io.BytesIO(archive.read("export.shp")),
            shx=io.BytesIO(archive.read("export.shx")),
            dbf=io.BytesIO(archive.read("export.dbf")),
        )
        with reader:
            return {f.name for f in reader.fields if f.name != "DeletionFlag"}

    def test_export_preserves_the_hole(self):
        _wizard, archive = self._export(domain="[('code', '=', 'D1')]")
        records = self._read_records(archive)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(records[0].shape.parts), 2)

    def test_import_autodetects_a_zipped_shapefile(self):
        archive_bytes = self._prepare_shapefile_zip(
            [
                Polygon(
                    [
                        (-99.30, 19.60),
                        (-99.25, 19.60),
                        (-99.25, 19.65),
                        (-99.30, 19.65),
                        (-99.30, 19.60),
                    ]
                )
            ]
        )
        before = self.Parcel.search_count([])
        wizard = self._import(archive_bytes)
        self.env.flush_all()
        self.assertEqual(wizard.imported_count, 1)
        self.assertEqual(self.Parcel.search_count([]), before + 1)
        created = self.Parcel.search([], order="id desc", limit=1)
        self.assertTrue(created.boundary, "the imported record has no geometry")
        self.assertAlmostEqual(created.boundary.bounds[0], -99.30, places=4)

    def test_import_missing_dbf_is_refused(self):
        shp_buf, shx_buf, dbf_buf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        writer = shapefile.Writer(
            shp=shp_buf, shx=shx_buf, dbf=dbf_buf, shapeType=shapefile.POINT
        )
        writer.field("label", "C", size=10)
        writer.point(0, 0)
        writer.record(label="x")
        writer.close()
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as archive:
            archive.writestr("t.shp", shp_buf.getvalue())
            archive.writestr("t.shx", shx_buf.getvalue())
        with self.assertRaises(UserError):
            self._import(zip_buf.getvalue())

    def test_a_parcel_survives_shapefile_export_and_reimport(self):
        for srid in ("4326", "3857"):
            with self.subTest(output_srid=srid):
                original = self.parcels[0].boundary
                _wizard, archive = self._export(
                    output_srid=srid, domain="[('code', '=', 'N1')]"
                )
                zip_bytes = io.BytesIO()
                with zipfile.ZipFile(zip_bytes, "w") as out:
                    for name in archive.namelist():
                        out.writestr(name, archive.read(name))
                before = self.Parcel.search_count([])
                self._import(zip_bytes.getvalue())
                self.env.flush_all()
                self.assertEqual(self.Parcel.search_count([]), before + 1)
                reimported = self.Parcel.search([], order="id desc", limit=1).boundary
                self.assertLess(
                    original.symmetric_difference(reimported).area,
                    1e-8,
                    f"a shapefile round trip through EPSG:{srid} moved the parcel:\n"
                    f"  before {original.wkt}\n  after  {reimported.wkt}",
                )

    def test_a_donut_survives_shapefile_export_and_reimport(self):
        original = self.donut.boundary
        _wizard, archive = self._export(domain="[('code', '=', 'D1')]")
        zip_bytes = io.BytesIO()
        with zipfile.ZipFile(zip_bytes, "w") as out:
            for name in archive.namelist():
                out.writestr(name, archive.read(name))
        self._import(zip_bytes.getvalue())
        self.env.flush_all()
        reimported = self.Parcel.search([], order="id desc", limit=1).boundary
        self.assertEqual(len(reimported.interiors), 1, "the hole was dropped")
        self.assertLess(
            original.symmetric_difference(reimported).area,
            1e-8,
            f"before {original.wkt}\nafter  {reimported.wkt}",
        )


@tagged("post_install", "-at_install", "geoengine_audit")
class TestGeoPackageRoundTrip(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Parcel = cls.env[IoParcel._name]
        cls.model_id = cls.env["ir.model"]._get_id(cls.Parcel._name)
        cls.geo_field_id = (
            cls.env["ir.model.fields"]._get(cls.Parcel._name, "boundary").id
        )
        cls.parcels = cls.Parcel.create(
            [
                {
                    "name": "North field",
                    "code": "N1",
                    "area": 12.5,
                    "boundary": (
                        "SRID=4326;POLYGON((-99.20 19.40,-99.10 19.40,"
                        "-99.10 19.50,-99.20 19.50,-99.20 19.40))"
                    ),
                },
                {
                    "name": "South field",
                    "code": "S1",
                    "area": 7.25,
                    "boundary": (
                        "SRID=4326;POLYGON((-99.20 19.20,-99.10 19.20,"
                        "-99.10 19.30,-99.20 19.30,-99.20 19.20))"
                    ),
                },
            ]
        )
        cls.donut = cls.Parcel.create(
            {
                "name": "Donut field",
                "code": "D1",
                "area": 3.0,
                "boundary": (
                    "SRID=4326;POLYGON("
                    "(-99.40 19.60,-99.30 19.60,-99.30 19.70,-99.40 19.70,-99.40 19.60),"
                    "(-99.38 19.62,-99.36 19.62,-99.36 19.64,-99.38 19.64,-99.38 19.62))"
                ),
            }
        )

    def _export(self, **overrides):
        vals = {
            "model_id": self.model_id,
            "geo_field_id": self.geo_field_id,
            "output_format": "geopackage",
            "output_srid": "4326",
        }
        vals.update(overrides)
        wizard = self.env["wizard.base.export.geodata"].create(vals)
        wizard.action_export()
        gpkg_bytes = base64.b64decode(wizard.output_file)
        con = sqlite3.connect(":memory:")
        con.deserialize(gpkg_bytes)
        return wizard, con, gpkg_bytes

    def _import(self, gpkg_bytes, **overrides):
        vals = {
            "model_id": self.model_id,
            "geo_field_id": self.geo_field_id,
            "file_data": base64.b64encode(gpkg_bytes),
            "file_name": "parcels.gpkg",
        }
        vals.update(overrides)
        wizard = self.env["wizard.base.import.geodata"].create(vals)
        wizard.action_import()
        return wizard

    def test_export_writes_the_required_system_tables(self):
        _wizard, con, _bytes = self._export()
        tables = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertTrue(
            {"gpkg_spatial_ref_sys", "gpkg_contents", "gpkg_geometry_columns"} <= tables
        )

    def test_export_identifies_itself_as_a_geopackage(self):
        _wizard, con, _bytes = self._export()
        (application_id,) = con.execute("PRAGMA application_id").fetchone()
        (user_version,) = con.execute("PRAGMA user_version").fetchone()
        self.assertEqual(application_id, 0x47504B47)
        self.assertEqual(user_version, 10300)

    def test_export_writes_one_row_per_parcel(self):
        _wizard, con, _bytes = self._export()
        (table_name,) = con.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
        ).fetchone()
        (count,) = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
        self.assertEqual(count, 3)

    def test_export_declares_the_output_srid(self):
        _wizard, con, _bytes = self._export(output_srid="3857")
        (srs_id,) = con.execute("SELECT srs_id FROM gpkg_geometry_columns").fetchone()
        self.assertEqual(srs_id, 3857)
        (definition,) = con.execute(
            "SELECT definition FROM gpkg_spatial_ref_sys WHERE srs_id=3857"
        ).fetchone()
        self.assertIn("3857", definition)

    def _first_geom_blob(self, con):
        (table_name,) = con.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
        ).fetchone()
        (blob,) = con.execute(f'SELECT geom FROM "{table_name}"').fetchone()
        return blob

    def test_export_reprojects_rather_than_relabelling(self):
        _wizard, con, _bytes = self._export(
            output_srid="3857", domain="[('code', '=', 'N1')]"
        )
        wkb_bytes, srid = _gpb_to_wkb(self._first_geom_blob(con))
        self.assertEqual(srid, 3857)
        geom = wkb_loads(wkb_bytes)
        self.assertGreater(
            abs(geom.bounds[0]), 180, "coordinates still look like degrees"
        )

    def test_export_preserves_the_hole(self):
        _wizard, con, _bytes = self._export(domain="[('code', '=', 'D1')]")
        wkb_bytes, _srid = _gpb_to_wkb(self._first_geom_blob(con))
        geom = wkb_loads(wkb_bytes)
        self.assertEqual(len(geom.interiors), 1)

    def test_import_missing_geometry_columns_table_is_refused(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE gpkg_contents (table_name TEXT, data_type TEXT)")
        con.commit()
        with self.assertRaises(UserError):
            self._import(con.serialize())

    def test_a_parcel_survives_geopackage_export_and_reimport(self):
        for srid in ("4326", "3857"):
            with self.subTest(output_srid=srid):
                original = self.parcels[0].boundary
                _wizard, _con, gpkg_bytes = self._export(
                    output_srid=srid, domain="[('code', '=', 'N1')]"
                )
                before = self.Parcel.search_count([])
                self._import(gpkg_bytes)
                self.env.flush_all()
                self.assertEqual(self.Parcel.search_count([]), before + 1)
                reimported = self.Parcel.search([], order="id desc", limit=1).boundary
                self.assertLess(
                    original.symmetric_difference(reimported).area,
                    1e-8,
                    f"a GeoPackage round trip through EPSG:{srid} moved the parcel:\n"
                    f"  before {original.wkt}\n  after  {reimported.wkt}",
                )

    def test_a_donut_survives_geopackage_export_and_reimport(self):
        original = self.donut.boundary
        _wizard, _con, gpkg_bytes = self._export(domain="[('code', '=', 'D1')]")
        self._import(gpkg_bytes)
        self.env.flush_all()
        reimported = self.Parcel.search([], order="id desc", limit=1).boundary
        self.assertEqual(len(reimported.interiors), 1, "the hole was dropped")
        self.assertLess(
            original.symmetric_difference(reimported).area,
            1e-8,
            f"before {original.wkt}\nafter  {reimported.wkt}",
        )

    def test_the_id_field_does_not_collide_with_the_hardcoded_column(self):
        fields_model = self.env["ir.model.fields"]
        id_field = fields_model.search(
            [("model", "=", self.Parcel._name), ("name", "=", "id")], limit=1
        )
        name_field = fields_model.search(
            [("model", "=", self.Parcel._name), ("name", "=", "name")], limit=1
        )
        self.assertTrue(id_field, "the fixture must expose its own id field")
        self.assertTrue(name_field)
        _wizard, con, _raw = self._export(
            property_field_ids=[(6, 0, (id_field | name_field).ids)]
        )
        (table_name,) = con.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
        ).fetchone()
        columns = [row[1] for row in con.execute(f'PRAGMA table_info("{table_name}")')]
        self.assertEqual(
            len(columns), len(set(columns)), f"duplicate columns: {columns}"
        )
        self.assertIn("id", columns)
        self.assertIn("id1", columns)

    def test_reserved_geopackage_names_are_taken_before_the_fields(self):
        unique = self.env["wizard.base.export.geodata"]._name_deduplicator(
            reserved=("fid", "geom")
        )
        self.assertEqual(unique("fid"), "fid1")
        self.assertEqual(unique("geom"), "geom1")
        self.assertEqual(unique("area"), "area")

    def test_the_dbf_deduplicator_still_truncates_to_ten(self):
        unique = self.env["wizard.base.export.geodata"]._name_deduplicator(
            max_length=10
        )
        self.assertEqual(unique("a_very_long_field_name"), "a_very_lon")
        self.assertEqual(unique("a_very_long_other_name"), "a_very_lo1")
