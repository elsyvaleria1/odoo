from typing import Any

from odoo import api, fields, models

from .geo_types import GEO_FIELD_TTYPES


class IrModelField(models.Model):
    _inherit = "ir.model.fields"

    geo_type = fields.Selection(
        selection=[
            ("LineString", "LineString"),
            ("Point", "Point"),
            ("Polygon", "Polygon"),
            ("MultiPoint", "MultiPoint"),
            ("MultiLineString", "MultiLineString"),
            ("MultiPolygon", "MultiPolygon"),
        ],
        string="PostGIS Type",
        help="Geometry type for PostGIS fields",
    )
    dim = fields.Selection(
        selection=[
            ("2", "2"),
            ("3", "3"),
            ("4", "4"),
        ],
        string="PostGIS Dimension",
        help="Spatial dimension for geometry fields (2D, 3D, or 4D)",
    )
    srid = fields.Integer(
        string="SRID",
        help="Spatial Reference System Identifier for geometry fields",
    )
    is_geo_field = fields.Boolean(
        string="Is Geometry Field",
        compute="_compute_is_geo_field",
        help="Technical field: whether ttype is one of the PostGIS geometry types.",
    )

    def _prepare_field_vals(self, field: Any, model_id: int) -> dict[str, Any]:
        vals = super()._prepare_field_vals(field, model_id)
        if field.type in GEO_FIELD_TTYPES:
            return vals | {
                "geo_type": field.geo_type,
                "srid": field.srid,
                "dim": field.dim,
            }
        return vals | {"geo_type": None, "srid": None, "dim": None}

    @api.depends("ttype")
    def _compute_is_geo_field(self) -> None:
        for rec in self:
            rec.is_geo_field = rec.ttype in GEO_FIELD_TTYPES
