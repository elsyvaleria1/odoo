import base64
import io
import sqlite3
import zipfile
from unittest.mock import patch

import shapefile

from odoo import fields
from odoo.exceptions import UserError
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.geoengine.wizards import wizard_base_import_geodata
from odoo.addons.test_geoengine.models.geo_io_fidelity import FidelityParcel


@tagged("post_install", "-at_install", "geoengine_audit")
class TestGeoIoFidelity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Parcel = cls.env[FidelityParcel._name]
        cls.model_id = cls.env["ir.model"]._get_id(FidelityParcel._name)
        field = cls.env["ir.model.fields"]._get
        cls.geo_field_id = field(FidelityParcel._name, "boundary").id
        cls.note_field = field(FidelityParcel._name, "note")
        cls.irrigated_field = field(FidelityParcel._name, "irrigated")
        cls.owner_field = field(FidelityParcel._name, "owner_id")

    def _export(self, output_format, records):
        wizard = self.env["wizard.base.export.geodata"].create(
            {
                "model_id": self.model_id,
                "geo_field_id": self.geo_field_id,
                "property_field_ids": [
                    fields.Command.set([self.note_field.id, self.irrigated_field.id])
                ],
                "domain": f"[('id', 'in', {records.ids})]",
                "output_format": output_format,
            }
        )
        wizard.action_export()
        return base64.b64decode(wizard.output_file)

    def _exported_rows(self, output_format, records):
        raw = self._export(output_format, records)
        if output_format == "geojson":
            return [
                (f["properties"]["note"], f["properties"]["irrigated"])
                for f in json_loads(raw)["features"]
            ]
        if output_format == "shapefile":
            archive = zipfile.ZipFile(io.BytesIO(raw))
            reader = shapefile.Reader(
                shp=io.BytesIO(archive.read("export.shp")),
                shx=io.BytesIO(archive.read("export.shx")),
                dbf=io.BytesIO(archive.read("export.dbf")),
            )
            with reader:
                return [
                    (record["note"] or None, record["irrigated"])
                    for record in reader.records()
                ]
        con = sqlite3.connect(":memory:")
        con.deserialize(raw)
        table = FidelityParcel._name.replace(".", "_")
        return [
            (note, bool(irrigated))
            for note, irrigated in con.execute(f'SELECT note, irrigated FROM "{table}"')
        ]

    def test_an_empty_value_exports_as_empty_in_every_format(self):
        parcel = self.Parcel.create(
            {"name": "p", "boundary": "POINT(-99.1 19.4)", "irrigated": False}
        )
        for output_format in ("geojson", "shapefile", "geopackage"):
            with self.subTest(output_format=output_format):
                self.assertEqual(
                    self._exported_rows(output_format, parcel), [(None, False)]
                )

    def test_a_record_without_geometry_is_left_out(self):
        parcels = self.Parcel.create(
            [
                {"name": "drawn", "boundary": "POINT(-99.1 19.4)", "note": "x"},
                {"name": "blank", "note": "y"},
            ]
        )
        self.assertEqual(self._exported_rows("geojson", parcels), [("x", False)])

    def _shapefile_zip(self):
        buffers = io.BytesIO(), io.BytesIO(), io.BytesIO()
        writer = shapefile.Writer(
            shp=buffers[0], shx=buffers[1], dbf=buffers[2], shapeType=shapefile.POINT
        )
        writer.field("owner", "C", size=50)
        for index in range(3):
            writer.point(-99.1 + index, 19.4)
            writer.record(owner="Shared Owner")
        writer.close()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
            for name, buffer in zip(("t.shp", "t.shx", "t.dbf"), buffers, strict=True):
                zipped.writestr(name, buffer.getvalue())
        return archive.getvalue()

    def _import_wizard(self, raw, **values):
        return self.env["wizard.base.import.geodata"].create(
            {
                "model_id": self.model_id,
                "geo_field_id": self.geo_field_id,
                "file_data": base64.b64encode(raw),
            }
            | values
        )

    def test_a_shapefile_too_large_once_unzipped_is_refused(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
            zipped.writestr("t.shp", bytes(1_000_000))
            zipped.writestr("t.shx", b"")
            zipped.writestr("t.dbf", b"")
        wizard = self._import_wizard(archive.getvalue())
        with (
            patch.object(wizard_base_import_geodata, "MAX_IMPORT_BYTES", 100_000),
            self.assertRaisesRegex(UserError, "once unzipped"),
        ):
            wizard._read_geojson()

    def test_a_repeated_name_is_looked_up_once(self):
        owner = self.env["res.partner"].create({"name": "Shared Owner"})
        wizard = self._import_wizard(
            self._shapefile_zip(),
            mapping_lines=[
                fields.Command.create(
                    {"property_name": "owner", "field_id": self.owner_field.id}
                )
            ],
        )
        Partner = type(self.env["res.partner"])
        with patch.object(
            Partner, "name_search", autospec=True, side_effect=Partner.name_search
        ) as name_search:
            wizard.action_import()
        self.assertEqual(name_search.call_count, 1)
        self.assertEqual(
            self.Parcel.search([("owner_id", "=", owner.id)]).mapped("owner_id"),
            owner,
        )
        self.assertEqual(wizard.imported_count, 3)

    def test_a_geopackage_srs_id_is_resolved_to_its_epsg_code(self):
        parcel = self.Parcel.create({"name": "p", "boundary": "POINT(-99.1 19.4)"})
        con = sqlite3.connect(":memory:")
        con.deserialize(self._export("geopackage", parcel))
        con.execute(
            "INSERT INTO gpkg_spatial_ref_sys VALUES "
            "('WGS 84 alias', 100001, 'EPSG', 4326, 'undefined', '')"
        )
        con.execute("UPDATE gpkg_geometry_columns SET srs_id = 100001")
        con.commit()
        wizard = self._import_wizard(con.serialize())
        wizard._onchange_file_data()
        self.assertEqual(wizard.detected_crs, "EPSG:4326")
        wizard.action_import()
        imported = self.Parcel.search([("id", "!=", parcel.id)])
        self.assertAlmostEqual(imported.boundary.x, -99.1, delta=1e-9)
        self.assertAlmostEqual(imported.boundary.y, 19.4, delta=1e-9)

    def test_a_3d_geojson_imports_into_a_2d_field(self):
        collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [-99.1 + i, 19.4, 2240],
                    },
                    "properties": {"name": f"z{i}"},
                }
                for i in range(3)
            ],
        }
        wizard = self._import_wizard(json_dumps_bytes(collection))
        wizard.action_import()
        self.assertEqual(wizard.imported_count, 3)

    def test_a_damaged_zip_member_is_reported_not_raised(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
            for name in ("t.shp", "t.shx", "t.dbf"):
                zipped.writestr(name, bytes(5000))
        raw = bytearray(archive.getvalue())
        local_header = raw.find(b"PK\x03\x04")
        raw[local_header + 14 : local_header + 18] = b"\x00\x00\x00\x00"
        central = raw.find(b"PK\x01\x02")
        raw[central + 16 : central + 20] = b"\x00\x00\x00\x00"
        wizard = self._import_wizard(bytes(raw))
        result = wizard._onchange_file_data()
        self.assertIn("damaged", result["warning"]["message"])
