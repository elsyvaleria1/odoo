import logging

from odoo import api, fields, models
from odoo.tools import SQL, LazyTranslate

_lt = LazyTranslate(__name__)
_logger = logging.getLogger(__name__)

PLACE_REUSE_M = 50

POI_CATEGORIES = {"amenity", "shop", "tourism", "craft", "office", "healthcare"}

PLACE_TYPE_LABELS = {
    "restaurant": _lt("Restaurant"),
    "fast_food": _lt("Food Stand"),
    "food_court": _lt("Food Court"),
    "cafe": _lt("Café"),
    "bar": _lt("Bar"),
    "pub": _lt("Bar"),
    "fuel": _lt("Gas Station"),
    "car_wash": _lt("Car Wash"),
    "car_repair": _lt("Mechanic"),
    "tyres": _lt("Tire Shop"),
    "parking": _lt("Parking"),
    "convenience": _lt("Convenience Store"),
    "supermarket": _lt("Supermarket"),
    "general": _lt("Store"),
    "marketplace": _lt("Market"),
    "hardware": _lt("Hardware Store"),
    "doityourself": _lt("Hardware Store"),
    "agrarian": _lt("Farm Supply Store"),
    "butcher": _lt("Butcher"),
    "bakery": _lt("Bakery"),
    "greengrocer": _lt("Greengrocer"),
    "florist": _lt("Florist"),
    "pharmacy": _lt("Pharmacy"),
    "hospital": _lt("Hospital"),
    "clinic": _lt("Clinic"),
    "doctors": _lt("Doctor"),
    "bank": _lt("Bank"),
    "atm": _lt("ATM"),
    "hotel": _lt("Hotel"),
    "motel": _lt("Motel"),
    "school": _lt("School"),
    "townhall": _lt("Town Hall"),
    "place_of_worship": _lt("Church"),
    "warehouse": _lt("Warehouse"),
}


class DeviceGpsPlace(models.Model):
    _name = "device.gps.place"
    _description = "Place Outside Geofences"
    _rec_name = "label"

    latitude = fields.Float(
        digits=(9, 6),
        readonly=True,
    )
    longitude = fields.Float(
        digits=(9, 6),
        readonly=True,
    )
    the_point = fields.GeoPoint(
        readonly=True,
        srid=4326,
    )
    name = fields.Char(
        readonly=True,
        help="The place's own name, when mapped.",
    )
    osm_category = fields.Char(readonly=True)
    osm_type = fields.Char(readonly=True)
    address = fields.Char(
        readonly=True,
        help="Street and locality.",
    )
    label = fields.Char(compute="_compute_label")

    @api.depends("name", "osm_category", "osm_type", "address")
    def _compute_label(self):
        lang = self.env.lang or "en_US"
        for place in self:
            what = ""
            if place.osm_category in POI_CATEGORIES:
                kind = PLACE_TYPE_LABELS.get(place.osm_type)
                kind = kind.translate(lang) if kind else ""
                what = (
                    f"{place.name} ({kind})"
                    if place.name and kind
                    else place.name or kind
                )
            elif place.name and place.name not in (place.address or ""):
                what = place.name
            place.label = " · ".join(filter(None, [what, place.address]))

    @api.model
    def _find_near(self, latitude, longitude):
        self.flush_model(["the_point"])
        self.env.cr.execute(
            SQL(
                """
                SELECT id FROM device_gps_place
                 WHERE ST_DWithin(the_point::geography,
                                  ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                                  %s)
                 ORDER BY the_point::geography
                          <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                 LIMIT 1
                """,
                longitude,
                latitude,
                PLACE_REUSE_M,
                longitude,
                latitude,
            )
        )
        row = self.env.cr.fetchone()
        return self.browse(row[0]) if row else self.browse()

    @api.model
    def _look_up(self, latitude, longitude):
        place = self._find_near(latitude, longitude)
        if place:
            return place
        result = (
            self.env["geocoder"]._call_openstreetmap_reverse(latitude, longitude) or {}
        )
        address = result.get("address") or {}
        locality = next(
            filter(
                None,
                (
                    address.get(key)
                    for key in ("village", "town", "city", "hamlet", "municipality")
                ),
            ),
            None,
        )
        return self.create(
            {
                "latitude": latitude,
                "longitude": longitude,
                "the_point": f"POINT({longitude} {latitude})",
                "name": result.get("name") or False,
                "osm_category": result.get("class") or result.get("category") or False,
                "osm_type": result.get("type") or False,
                "address": ", ".join(filter(None, [address.get("road"), locality]))
                or False,
            }
        )
