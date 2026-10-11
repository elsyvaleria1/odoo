from odoo import api, fields, models

CLIENT_AREA_FALLBACK_RADIUS_M = 150


class ResPartner(models.Model):
    _inherit = "res.partner"

    client_the_point = fields.GeoPoint(
        string="Client GPS Point",
        compute="_compute_client_the_point",
        store=True,
        srid=4326,
        help="Point built from Geo Latitude/Geo Longitude (Partner "
        "Assignment), for the Client Locations map.",
    )
    client_geofence_ids = fields.One2many(
        comodel_name="device.geo.fence",
        inverse_name="partner_id",
        string="Client Parcels",
    )
    client_salesperson_name = fields.Char(
        related="user_id.name",
        string="Salesperson Name",
        help="Plain-text mirror of Salesperson, for map layers that can "
        "only carry a char/text field (Client Locations overlay's "
        "color_field_id) alongside the geometry.",
    )
    client_the_area = fields.GeoMultiPolygon(
        string="Client Area",
        compute="_compute_client_the_area",
        store=True,
        srid=4326,
        help="The client's own mapped parcel(s) when any exist, otherwise a "
        f"{CLIENT_AREA_FALLBACK_RADIUS_M} m circle around Geo Latitude/Geo "
        "Longitude, so every client with either kind of location can be "
        "drawn on a single polygon layer.",
    )

    @api.depends("partner_latitude", "partner_longitude")
    def _compute_client_the_point(self) -> None:
        for partner in self:
            if partner.partner_latitude or partner.partner_longitude:
                partner.client_the_point = (
                    f"POINT({partner.partner_longitude} {partner.partner_latitude})"
                )
            else:
                partner.client_the_point = False

    @api.depends(
        "partner_latitude",
        "partner_longitude",
        "client_geofence_ids.the_geom",
        "client_geofence_ids.active",
        "client_geofence_ids.area_type",
    )
    def _compute_client_the_area(self) -> None:
        areas = self._client_area_by_partner()
        for partner in self:
            partner.client_the_area = areas.get(partner.id) or False

    def _client_area_by_partner(self):
        partner_ids = self.ids
        if not partner_ids:
            return {}
        self.env["device.geo.fence"].flush_model(
            ["active", "area_type", "partner_id", "the_geom"]
        )
        self.flush_recordset(["partner_latitude", "partner_longitude"])
        self.env.cr.execute(
            """
            WITH parcels AS (
                SELECT partner_id,
                       ST_Multi(ST_CollectionExtract(ST_Union(
                           ST_MakeValid(ST_Transform(the_geom, 4326))
                       ), 3)) AS geom
                  FROM device_geo_fence
                 WHERE area_type = 'parcel'
                   AND active
                   AND partner_id = ANY(%(ids)s)
                   AND the_geom IS NOT NULL
                 GROUP BY partner_id
            )
            SELECT p.id, ST_AsText(COALESCE(
                parcels.geom,
                CASE
                    WHEN p.partner_latitude != 0 OR p.partner_longitude != 0
                    THEN ST_Multi(ST_Buffer(
                        ST_SetSRID(
                            ST_MakePoint(p.partner_longitude, p.partner_latitude), 4326
                        )::geography,
                        %(radius)s
                    )::geometry)
                END
            ))
              FROM res_partner p
              LEFT JOIN parcels ON parcels.partner_id = p.id
             WHERE p.id = ANY(%(ids)s)
            """,
            {"ids": partner_ids, "radius": CLIENT_AREA_FALLBACK_RADIUS_M},
        )
        return dict(self.env.cr.fetchall())
