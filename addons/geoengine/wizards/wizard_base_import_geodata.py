import base64
import io
import logging
import sqlite3
import struct
import zipfile
from typing import Any

import shapefile
from pyproj import CRS
from pyproj.exceptions import CRSError
from shapely import set_srid
from shapely.errors import ShapelyError
from shapely.geometry import mapping, shape
from shapely.wkb import loads as wkb_loads

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Field
from odoo.libs.json import loads as json_loads

from ..models.fields import _srid_from_crs_member
from ..models.geo_types import DISPLAY_SRID, GEO_FIELD_TTYPES

logger = logging.getLogger(__name__)


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


_GPB_ENVELOPE_SIZE_BY_CODE = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def _gpb_to_wkb(blob: bytes) -> tuple[bytes, int]:
    if blob[0:2] != b"GP":
        raise ValueError("Not a GeoPackage geometry blob (missing GP magic).")
    flags = blob[3]
    byte_order = "<" if flags & 0x01 else ">"
    srid = struct.unpack_from(byte_order + "i", blob, 4)[0]
    envelope_code = (flags >> 1) & 0x07
    wkb_start = 8 + _GPB_ENVELOPE_SIZE_BY_CODE.get(envelope_code, 0)
    return blob[wkb_start:], srid


SRID_ASSUMED_KEY = "_geoengine_srid_assumed"

MAX_IMPORT_FEATURES = 50_000


MAX_IMPORT_BYTES = 64 * 1024 * 1024


class WizardBaseImportGeodata(models.TransientModel):
    _name = "wizard.base.import.geodata"
    _description = "Geo Import Wizard"

    model_id = fields.Many2one(
        comodel_name="ir.model",
        help="Model to import records into (must have geo fields)",
    )
    model_name = fields.Char(
        related="model_id.model",
        string="Technical Name",
        readonly=True,
    )

    file_data = fields.Binary(
        help="GeoJSON file (.geojson or .json), a zipped Shapefile (.zip) "
        "containing .shp, .shx and .dbf (optionally a .prj), or a GeoPackage "
        "(.gpkg). The format is detected automatically from the file's "
        "contents."
    )
    file_name = fields.Char()

    geo_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        domain=f"[('model_id', '=', model_id), ('ttype', 'in', {list(GEO_FIELD_TTYPES)})]",
        help="Target field for imported geometries",
    )
    name_property = fields.Char(
        help="GeoJSON property to use as record name (leave empty to auto-generate)"
    )
    mapping_lines = fields.One2many(
        comodel_name="wizard.base.import.geodata.mapping",
        inverse_name="wizard_id",
        help="Map GeoJSON properties to model fields",
    )

    skip_invalid = fields.Boolean(
        default=True,
        help="Skip features with invalid geometries instead of aborting",
    )

    feature_count = fields.Integer(readonly=True)
    preview_properties = fields.Text(
        readonly=True,
        help="Properties found in the GeoJSON file",
    )

    imported_count = fields.Integer(readonly=True)
    detected_crs = fields.Char(
        readonly=True,
        help="The coordinate system the file declares, or the assumption made "
        "when it declares none.",
    )

    @api.onchange("file_data")
    def _onchange_file_data(self) -> dict | None:
        if not self.file_data:
            self._update_preview(None)
            return None

        try:
            geojson_data = self._read_geojson()
        except (UserError, ValueError, sqlite3.Error) as e:
            self._update_preview(None)
            return {
                "warning": {
                    "title": self.env._("Invalid File"),
                    "message": self.env._("Could not parse the uploaded file: %s")
                    % str(e),
                }
            }

        self._update_preview(geojson_data)
        return None

    def _update_preview(self, geojson_data: dict | None) -> None:
        if not geojson_data:
            self.feature_count = 0
            self.preview_properties = ""
            self.detected_crs = ""
            return
        features = geojson_data.get("features", [])
        self.feature_count = len(features)
        all_props = set()
        for feat in features[:100]:
            if props := feat.get("properties"):
                all_props.update(props.keys())
        self.preview_properties = ", ".join(sorted(all_props)) if all_props else ""
        self.detected_crs = self._crs_note(geojson_data) or (
            f"EPSG:{self._get_srid(geojson_data)}"
        )

    def _crs_note(self, geojson_data: dict) -> str:
        if geojson_data.get(SRID_ASSUMED_KEY):
            return self.env._(
                "The file names no coordinate system; WGS 84 (EPSG:4326) was assumed."
            )
        return ""

    def _read_geojson(self) -> dict:
        if len(self.file_data or b"") > MAX_IMPORT_BYTES / 3 * 4:
            raise UserError(
                self.env._(
                    "This file is larger than the %(maximum)d MB import limit.",
                    maximum=MAX_IMPORT_BYTES // (1024 * 1024),
                ),
            )
        raw = base64.b64decode(self.file_data)
        if raw[:2] == b"PK":
            return self._shapefile_to_geojson(raw)
        if raw[:16] == b"SQLite format 3\x00":
            return self._geopackage_to_geojson(raw)
        return json_loads(raw.decode("utf-8"))

    def _shapefile_to_geojson(self, raw: bytes) -> dict:
        try:
            archive = zipfile.ZipFile(
                io.BytesIO(raw)
            )
        except zipfile.BadZipFile as e:
            raise UserError(
                self.env._("Not a valid GeoJSON file, nor a valid .zip archive.")
            ) from e

        members = {}
        for info in archive.infolist():
            ext = info.filename.rsplit(".", 1)[-1].lower()
            if ext in ("shp", "shx", "dbf", "prj"):
                members.setdefault(ext, info)
        if sum(info.file_size for info in members.values()) > MAX_IMPORT_BYTES:
            raise UserError(
                self.env._(
                    "This shapefile is larger than the %(maximum)d MB import "
                    "limit once unzipped.",
                    maximum=MAX_IMPORT_BYTES // (1024 * 1024),
                ),
            )
        try:
            parts = {
                ext: io.BytesIO(archive.read(info))
                for ext, info in members.items()
                if ext != "prj"
            }
            prj_text = (
                archive.read(members["prj"]).decode("utf-8", errors="replace")
                if "prj" in members
                else None
            )
        except zipfile.BadZipFile as e:
            raise UserError(
                self.env._("The .zip archive is damaged: %s", str(e))
            ) from e

        missing = {"shp", "shx", "dbf"} - parts.keys()
        if missing:
            raise UserError(
                self.env._(
                    "The uploaded .zip is missing %(missing)s. A shapefile "
                    "upload needs .shp, .shx and .dbf together in one archive.",
                    missing=", ".join(f".{ext}" for ext in sorted(missing)),
                ),
            )

        try:
            reader = shapefile.Reader(
                shp=parts["shp"], shx=parts["shx"], dbf=parts["dbf"]
            )
        except Exception as e:
            raise UserError(
                self.env._("Could not read the shapefile: %s") % str(e)
            ) from e

        features = []
        with reader:
            for shape_record in reader.shapeRecords():
                try:
                    geometry = shape_record.shape.__geo_interface__
                except (
                    shapefile.GeoJSON_Error,
                    shapefile.RingSamplingError,
                    shapefile.ShapefileException,
                ):
                    geometry = None
                features.append(
                    {
                        "type": "Feature",
                        "geometry": geometry,
                        "properties": shape_record.record.as_dict(),
                    }
                )

        geojson_data = {"type": "FeatureCollection", "features": features}
        srid = self._srid_from_prj(prj_text) if prj_text else None
        if srid:
            geojson_data["crs"] = {
                "type": "name",
                "properties": {"name": f"EPSG:{srid}"},
            }
        else:
            geojson_data[SRID_ASSUMED_KEY] = True
        return geojson_data

    def _srid_from_prj(self, wkt_text: str) -> int | None:
        try:
            return CRS.from_wkt(wkt_text).to_epsg()
        except CRSError:
            return None

    def _geopackage_to_geojson(self, raw: bytes) -> dict:
        con = sqlite3.connect(":memory:")
        try:
            try:
                con.deserialize(raw)
            except sqlite3.Error as e:
                raise UserError(
                    self.env._("Could not read the GeoPackage: %s") % str(e)
                ) from e

            cur = con.cursor()
            try:
                cur.execute(
                    "SELECT c.table_name, g.column_name, g.srs_id "
                    "FROM gpkg_contents c "
                    "JOIN gpkg_geometry_columns g ON g.table_name = c.table_name "
                    "WHERE c.data_type = 'features' "
                    "ORDER BY c.table_name LIMIT 1"
                )
            except sqlite3.OperationalError as e:
                raise UserError(
                    self.env._("Not a valid GeoPackage: %s") % str(e)
                ) from e
            row = cur.fetchone()
            if row is None:
                raise UserError(
                    self.env._("The GeoPackage has no feature table to import.")
                )
            table_name, geom_column, srs_id = row

            cur.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")
            prop_columns = [r[1] for r in cur.fetchall() if r[1] != geom_column]
            select_list = ", ".join(
                _quote_identifier(c) for c in (geom_column, *prop_columns)
            )
            cur.execute(f"SELECT {select_list} FROM {_quote_identifier(table_name)}")

            features = []
            blob_srs_id = None
            for record in cur.fetchall():
                blob = record[0]
                geometry = None
                if blob is not None:
                    try:
                        wkb_bytes, this_srs_id = _gpb_to_wkb(blob)
                        geometry = mapping(wkb_loads(wkb_bytes))
                        if this_srs_id > 0 and blob_srs_id is None:
                            blob_srs_id = this_srs_id
                    except ShapelyError, ValueError, struct.error:
                        geometry = None
                features.append(
                    {
                        "type": "Feature",
                        "geometry": geometry,
                        "properties": dict(zip(prop_columns, record[1:], strict=True)),
                    }
                )
            srid = self._gpkg_epsg_code(
                cur, srs_id if srs_id and srs_id > 0 else blob_srs_id
            )
        finally:
            con.close()

        geojson_data = {"type": "FeatureCollection", "features": features}
        if srid:
            geojson_data["crs"] = {
                "type": "name",
                "properties": {"name": f"EPSG:{srid}"},
            }
        else:
            geojson_data[SRID_ASSUMED_KEY] = True
        return geojson_data

    def _gpkg_epsg_code(self, cur: sqlite3.Cursor, srs_id: int | None) -> int | None:
        if not srs_id:
            return None
        cur.execute(
            "SELECT organization, organization_coordsys_id, definition "
            "FROM gpkg_spatial_ref_sys WHERE srs_id = ?",
            (srs_id,),
        )
        if not (row := cur.fetchone()):
            return None
        organization, code, definition = row
        if (organization or "").upper() == "EPSG" and code and code > 0:
            return code
        return self._srid_from_prj(definition) if definition else None

    def action_preview(self):
        self.check_singleton()

        if not self.file_data:
            raise UserError(self.env._("Please upload a file first."))

        try:
            geojson_data = self._read_geojson()
        except Exception as e:
            raise UserError(self.env._("Invalid file: %s") % str(e)) from e

        self._update_preview(geojson_data)

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_import(self):
        self.check_singleton()

        if not self.model_id:
            raise UserError(self.env._("Please select a target model."))
        if not self.file_data:
            raise UserError(self.env._("Please upload a file."))
        if not self.geo_field_id:
            raise UserError(self.env._("Please select a geometry field."))

        try:
            geojson_data = self._read_geojson()
        except Exception as e:
            raise UserError(self.env._("Invalid file: %s") % str(e)) from e

        features = geojson_data.get("features", [])
        if not features:
            raise UserError(self.env._("No features found in the uploaded file."))

        if len(features) > MAX_IMPORT_FEATURES:
            raise UserError(
                self.env._(
                    "File contains %(count)d features. Maximum allowed is %(maximum)d.",
                    count=len(features),
                    maximum=MAX_IMPORT_FEATURES,
                ),
            )

        TargetModel = self.env[self.model_name]
        geo_field_name = self.geo_field_id.name

        field_map = {}
        for line in self.mapping_lines:
            if line.property_name and line.field_id:
                field_map[line.property_name] = line.field_id.name

        file_srid = self._get_srid(geojson_data)

        errors = []
        batch_vals = []
        record_by_name: dict[tuple[str, str], int] = {}

        for i, feature in enumerate(features):
            try:
                vals = self._feature_to_vals(
                    feature,
                    geo_field_name,
                    field_map,
                    file_srid,
                    record_by_name,
                )
                if vals:
                    batch_vals.append(vals)
            except Exception as e:
                if self.skip_invalid:
                    errors.append(f"Feature {i}: {e}")
                    continue
                raise UserError(
                    self.env._(
                        "Error importing feature %(index)d: %(error)s",
                        index=i,
                        error=str(e),
                    ),
                ) from e

        imported = len(batch_vals)
        if batch_vals:
            try:
                with self.env.cr.savepoint():
                    TargetModel.create(batch_vals)
            except Exception as batch_error:
                if not self.skip_invalid:
                    raise UserError(
                        self.env._("Import failed: %(error)s", error=str(batch_error))
                    ) from batch_error
                imported = self._create_one_by_one(TargetModel, batch_vals, errors)
        self.imported_count = imported

        if errors:
            logger.warning(
                "Geo import: %d errors skipped out of %d features",
                len(errors),
                len(features),
            )

        message = self.env._(
            "Imported %(imported)d of %(total)d features.",
            imported=imported,
            total=len(features),
        )
        crs_note = self._crs_note(geojson_data)
        if crs_note:
            message = f"{message} {crs_note}"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Import Complete"),
                "message": message,
                "type": "success" if not (errors or crs_note) else "warning",
                "sticky": bool(crs_note),
            },
        }

    def _create_one_by_one(self, target_model, batch_vals: list, errors: list) -> int:
        created = 0
        for index, vals in enumerate(batch_vals):
            try:
                with self.env.cr.savepoint():
                    target_model.create(vals)
                created += 1
            except Exception as e:
                logger.warning("Record %s was not imported", index, exc_info=True)
                errors.append(f"Record {index}: {e}")
        return created

    def _get_srid(self, geojson_data: dict) -> int:
        return _srid_from_crs_member(geojson_data.get("crs")) or DISPLAY_SRID

    def _feature_to_vals(
        self,
        feature: dict,
        geo_field_name: str,
        field_map: dict,
        file_srid: int,
        record_by_name: dict[tuple[str, str], int] | None = None,
    ) -> dict | None:
        geometry = feature.get("geometry")
        if not geometry:
            return None

        try:
            geom = shape(geometry)
        except Exception as e:
            raise UserError(self.env._("Invalid geometry: %s", str(e))) from e

        if geom.is_empty:
            return None

        vals = {geo_field_name: set_srid(geom, file_srid)}

        model_fields = self.env[self.model_name]._fields
        properties = feature.get("properties") or {}
        for prop_name, field_name in field_map.items():
            if prop_name in properties:
                vals[field_name] = self._import_value(
                    model_fields[field_name], properties[prop_name], record_by_name
                )

        if self.name_property and self.name_property in properties:
            if "name" in model_fields:
                vals.setdefault("name", str(properties[self.name_property]))

        return vals

    def _import_value(
        self,
        field: Field,
        value: Any,
        record_by_name: dict[tuple[str, str], int] | None = None,
    ) -> Any:
        if field.type != "many2one" or not value:
            return value
        if isinstance(value, (list, tuple)):
            return value[0] if value else False
        if isinstance(value, int):
            return value
        key = (field.comodel_name, str(value))
        if record_by_name is not None and key in record_by_name:
            return record_by_name[key]
        comodel = self.env[field.comodel_name]
        if match := comodel.name_search(str(value), limit=1):
            if record_by_name is not None:
                record_by_name[key] = match[0][0]
            return match[0][0]
        raise UserError(
            self.env._(
                "%(field)s: no %(model)s is named '%(value)s'.",
                field=field.name,
                model=comodel._description,
                value=value,
            )
        )
