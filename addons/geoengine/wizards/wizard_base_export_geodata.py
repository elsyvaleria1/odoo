import base64
import io
import json
import logging
import sqlite3
import struct
import zipfile
from datetime import date, datetime
from typing import Any

import shapefile
from pyproj import CRS
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.wkb import dumps as wkb_dumps

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Field

from ..models.fields import reproject
from ..models.geo_domain import parse_domain_text
from ..models.geo_types import GEO_FIELD_TTYPES
from .wizard_base_import_geodata import _quote_identifier

logger = logging.getLogger(__name__)


_SHAPE_TYPE_BY_GEO_TYPE = {
    "Point": shapefile.POINT,
    "MultiPoint": shapefile.MULTIPOINT,
    "LineString": shapefile.POLYLINE,
    "MultiLineString": shapefile.POLYLINE,
    "Polygon": shapefile.POLYGON,
    "MultiPolygon": shapefile.POLYGON,
}


_DBF_NUMERIC_TTYPES = {"integer", "float", "monetary"}


_DBF_BOOLEAN_TTYPES = {"boolean"}


_GPKG_GEOM_TYPES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
}


_GPKG_NUMERIC_TTYPES = {"integer": "INTEGER", "float": "REAL", "monetary": "REAL"}


_GPKG_SYSTEM_SCHEMA_SQL = """
CREATE TABLE gpkg_spatial_ref_sys (
    srs_name TEXT NOT NULL,
    srs_id INTEGER NOT NULL PRIMARY KEY,
    organization TEXT NOT NULL,
    organization_coordsys_id INTEGER NOT NULL,
    definition TEXT NOT NULL,
    description TEXT
);
CREATE TABLE gpkg_contents (
    table_name TEXT NOT NULL PRIMARY KEY,
    data_type TEXT NOT NULL,
    identifier TEXT UNIQUE,
    description TEXT DEFAULT '',
    last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
    srs_id INTEGER,
    CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
);
CREATE TABLE gpkg_geometry_columns (
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    geometry_type_name TEXT NOT NULL,
    srs_id INTEGER NOT NULL,
    z TINYINT NOT NULL,
    m TINYINT NOT NULL,
    CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
    CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
    CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id)
);
INSERT INTO gpkg_spatial_ref_sys VALUES
    ('Undefined cartesian SRS', -1, 'NONE', -1, 'undefined', 'undefined cartesian coordinate reference system'),
    ('Undefined geographic SRS', 0, 'NONE', 0, 'undefined', 'undefined geographic coordinate reference system');
"""


def _geom_to_gpb(geom, srid: int) -> bytes:
    flags = 0x01
    header = b"GP" + bytes([0, flags]) + struct.pack("<i", srid)
    return header + wkb_dumps(geom, byte_order=1)


MAX_EXPORT_FEATURES = 100_000

type ExportFeature = tuple[BaseGeometry, dict[str, Any]]


def _export_value(field: Field, value: Any) -> Any:
    if field.type == "many2one":
        return value[1] if value else None
    if value is False and field.type != "boolean":
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


MAX_EXPORT_BYTES = 64 * 1024 * 1024


def _geom_to_pyshp_parts(geom) -> tuple[str, tuple] | None:
    geom_type = geom.geom_type
    if geom_type == "Point":
        return "point", (geom.x, geom.y)
    if geom_type == "MultiPoint":
        return "multipoint", ([(p.x, p.y) for p in geom.geoms],)
    if geom_type == "LineString":
        return "line", ([list(geom.coords)],)
    if geom_type == "MultiLineString":
        return "line", ([list(line.coords) for line in geom.geoms],)
    if geom_type in ("Polygon", "MultiPolygon"):
        polygons = geom.geoms if geom_type == "MultiPolygon" else [geom]
        parts = []
        for polygon in polygons:
            oriented = orient(polygon, sign=-1.0)
            parts.append(list(oriented.exterior.coords))
            parts.extend(list(ring.coords) for ring in oriented.interiors)
        return "poly", (parts,)
    return None


class WizardBaseExportGeodata(models.TransientModel):
    _name = "wizard.base.export.geodata"
    _description = "Geo Export Wizard"

    model_id = fields.Many2one(
        comodel_name="ir.model",
        help="Model to export records from",
    )
    model_name = fields.Char(
        related="model_id.model",
        string="Technical Name",
        readonly=True,
    )

    geo_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        domain=f"[('model_id', '=', model_id), ('ttype', 'in', {list(GEO_FIELD_TTYPES)})]",
    )

    property_field_ids = fields.Many2many(
        comodel_name="ir.model.fields",
        domain="[('model_id', '=', model_id), "
        f"('ttype', 'not in', {list(GEO_FIELD_TTYPES)}), "
        "('ttype', 'not in', ['one2many', 'many2many', 'binary'])]",
        help="Fields to include as GeoJSON properties",
    )

    domain = fields.Char(
        default="[]",
        help="Domain to filter exported records",
    )

    output_format = fields.Selection(
        selection=[
            ("geojson", "GeoJSON"),
            ("shapefile", "Shapefile (.zip)"),
            ("geopackage", "GeoPackage (.gpkg)"),
        ],
        default="geojson",
        required=True,
        help="Shapefile is the format most GIS tools and field equipment "
        "accept; GeoPackage is the modern OGC standard (one file, no "
        "10-character field-name limit, real Multi* geometry types); "
        "GeoJSON keeps full property-type fidelity.",
    )

    output_srid = fields.Selection(
        selection=[
            ("4326", "WGS84 (EPSG:4326) - Standard GPS"),
            ("3857", "Web Mercator (EPSG:3857)"),
        ],
        default="4326",
        required=True,
        help="Coordinate Reference System for output file",
    )

    output_file = fields.Binary(readonly=True)
    output_filename = fields.Char(readonly=True)

    def action_export(self) -> dict:
        self.check_singleton()

        if not self.model_id:
            raise UserError(self.env._("Please select a source model."))
        if not self.geo_field_id:
            raise UserError(self.env._("Please select a geometry field."))

        TargetModel = self.env[self.model_name]  # pylint: disable=invalid-name
        geo_field_name = self.geo_field_id.name

        prop_field_names = self.property_field_ids.mapped("name")

        try:
            search_domain = parse_domain_text(self.env, self.domain)
        except Exception as e:
            raise UserError(self.env._("Invalid domain: %s") % str(e)) from e

        records = TargetModel.search(search_domain, limit=MAX_EXPORT_FEATURES + 1)

        if not records:
            raise UserError(self.env._("No records found matching the criteria."))

        if len(records) > MAX_EXPORT_FEATURES:
            raise UserError(
                self.env._(
                    "Export contains more than %(maximum)d records. "
                    "Please apply a filter to reduce the result set.",
                    maximum=MAX_EXPORT_FEATURES,
                ),
            )

        model_fields = TargetModel._fields
        geo_field = model_fields[geo_field_name]
        target_srid = int(self.output_srid)
        features = [
            (
                reproject(geometry, geo_field.srid, target_srid),
                {
                    "id": row["id"],
                    **{
                        fname: _export_value(model_fields[fname], row[fname])
                        for fname in prop_field_names
                    },
                },
            )
            for row, geometry in zip(
                records.read(prop_field_names),
                records.mapped(geo_field_name),
                strict=True,
            )
            if geometry and not geometry.is_empty
        ]

        base_filename = self.model_name.replace(".", "_")
        if self.output_format == "shapefile":
            output = self._prepare_shapefile_zip(features, geo_field.geo_type)
            self.output_filename = f"{base_filename}_export.zip"
        elif self.output_format == "geopackage":
            output = self._prepare_geopackage(
                features, geo_field.geo_type, base_filename
            )
            self.output_filename = f"{base_filename}_export.gpkg"
        else:
            output = self._prepare_geojson(features)
            self.output_filename = f"{base_filename}_export.geojson"

        if len(output) > MAX_EXPORT_BYTES:
            raise UserError(
                self.env._(
                    "This export is larger than the %(maximum)d MB limit. "
                    "Please apply a filter to reduce the result set.",
                    maximum=MAX_EXPORT_BYTES // (1024 * 1024),
                ),
            )

        self.output_file = base64.b64encode(output)

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _prepare_geojson(self, features: list[ExportFeature]) -> bytes:
        geojson_data: dict = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": mapping(geometry), "properties": props}
                for geometry, props in features
            ],
        }
        if self.output_srid != "4326":
            geojson_data["crs"] = {
                "type": "name",
                "properties": {"name": f"EPSG:{self.output_srid}"},
            }
        return json.dumps(geojson_data, indent=2, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _name_deduplicator(max_length: int | None = None, reserved: tuple = ()):
        used: set[str] = set(reserved)

        def unique(base: str) -> str:
            if max_length:
                base = base[:max_length]
            base = base or "field"
            candidate = base
            suffix = 1
            while candidate in used:
                tail = str(suffix)
                candidate = (
                    f"{base[: max_length - len(tail)]}{tail}"
                    if max_length
                    else f"{base}{tail}"
                )
                suffix += 1
            used.add(candidate)
            return candidate

        return unique

    def _dbf_field_defs(self) -> list[tuple[str, str, str]]:
        unique = self._name_deduplicator(max_length=10)
        defs = [(unique("id"), "id", "integer")]
        defs.extend((unique(f.name), f.name, f.ttype) for f in self.property_field_ids)
        return defs

    def _prepare_shapefile_zip(
        self, features: list[ExportFeature], geo_type: str | None
    ) -> bytes:
        shape_type = _SHAPE_TYPE_BY_GEO_TYPE.get(geo_type)
        if shape_type is None:
            raise UserError(
                self.env._(
                    "%(geo_type)s has no Shapefile equivalent.",
                    geo_type=geo_type,
                ),
            )

        dbf_defs = self._dbf_field_defs()
        shp_buf, shx_buf, dbf_buf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        writer = shapefile.Writer(
            shp=shp_buf, shx=shx_buf, dbf=dbf_buf, shapeType=shape_type
        )
        for dbf_name, _prop_key, ttype in dbf_defs:
            if ttype in _DBF_NUMERIC_TTYPES:
                writer.field(
                    dbf_name, "N", decimal=0 if ttype == "integer" else 6, size=18
                )
            elif ttype in _DBF_BOOLEAN_TTYPES:
                writer.field(dbf_name, "L")
            else:
                writer.field(dbf_name, "C", size=254)

        for geom, properties in features:
            parts = _geom_to_pyshp_parts(geom)
            if parts is None:
                raise UserError(
                    self.env._(
                        "%(geom_type)s has no Shapefile equivalent.",
                        geom_type=geom.geom_type,
                    ),
                )
            method_name, args = parts
            getattr(writer, method_name)(*args)
            writer.record(
                **{
                    dbf_name: properties.get(prop_key)
                    for dbf_name, prop_key, _ttype in dbf_defs
                }
            )
        writer.close()

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("export.shp", shp_buf.getvalue())
            archive.writestr("export.shx", shx_buf.getvalue())
            archive.writestr("export.dbf", dbf_buf.getvalue())
            archive.writestr(
                "export.prj", CRS.from_epsg(int(self.output_srid)).to_wkt()
            )
        return zip_buf.getvalue()

    def _gpkg_field_defs(self) -> list[tuple[str, str, str]]:
        unique = self._name_deduplicator(reserved=("fid", "geom"))
        defs = [(unique("id"), "id", "INTEGER")]
        defs.extend(
            (
                unique(f.name),
                f.name,
                "BOOLEAN"
                if f.ttype == "boolean"
                else _GPKG_NUMERIC_TTYPES.get(f.ttype, "TEXT"),
            )
            for f in self.property_field_ids
        )
        return defs

    def _prepare_geopackage(
        self, features: list[ExportFeature], geo_type: str | None, table_name: str
    ) -> bytes:
        if geo_type not in _GPKG_GEOM_TYPES:
            raise UserError(
                self.env._(
                    "%(geo_type)s has no GeoPackage equivalent.", geo_type=geo_type
                ),
            )
        geom_type_name = geo_type.upper()
        output_srid = int(self.output_srid)
        table = _quote_identifier(table_name)

        con = sqlite3.connect(":memory:")
        try:
            con.execute("PRAGMA application_id = 1196444487")
            con.execute("PRAGMA user_version = 10300")
            con.executescript(_GPKG_SYSTEM_SCHEMA_SQL)
            con.execute(
                "INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, 'EPSG', ?, ?, '')",
                (
                    f"EPSG:{output_srid}",
                    output_srid,
                    output_srid,
                    CRS.from_epsg(output_srid).to_wkt(),
                ),
            )

            field_defs = self._gpkg_field_defs()
            columns_sql = ", ".join(
                f"{_quote_identifier(name)} {sql_type}"
                for name, _key, sql_type in field_defs
            )
            con.execute(
                f"CREATE TABLE {table} "
                f"(fid INTEGER PRIMARY KEY AUTOINCREMENT, geom {geom_type_name}, "
                f"{columns_sql})"
            )
            con.execute(
                "INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', ?, ?, 0, 0)",
                (table_name, geom_type_name, output_srid),
            )
            con.execute(
                "INSERT INTO gpkg_contents "
                "(table_name, data_type, identifier, srs_id) VALUES (?, 'features', ?, ?)",
                (table_name, table_name, output_srid),
            )

            column_list = ", ".join(
                _quote_identifier(name) for name, _key, _t in field_defs
            )
            placeholders = ", ".join(["?"] * (1 + len(field_defs)))
            insert_sql = (
                f"INSERT INTO {table} (geom, {column_list}) VALUES ({placeholders})"
            )
            con.executemany(
                insert_sql,
                (
                    [
                        _geom_to_gpb(geom, output_srid),
                        *(properties.get(key) for _name, key, _t in field_defs),
                    ]
                    for geom, properties in features
                ),
            )
            con.commit()
            return con.serialize()
        finally:
            con.close()
