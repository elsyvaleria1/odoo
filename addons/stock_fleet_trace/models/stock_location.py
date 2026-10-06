from odoo import api, fields, models
from odoo.tools import SQL, ormcache


class StockLocation(models.Model):
    _inherit = "stock.location"

    trip_vehicle_id = fields.Many2one(
        comodel_name="resource.asset.vehicle",
        string="Vehicle",
        index="btree_not_null",
        ondelete="restrict",
        help="Vehicle whose load this location holds while it travels. Goods are "
        "here from loading until they are delivered, written off or unloaded.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        locations = super().create(vals_list)
        if any(vals.get("trip_vehicle_id") for vals in vals_list):
            self.env.registry.clear_cache()
        return locations

    def write(self, vals):
        result = super().write(vals)
        if "trip_vehicle_id" in vals or "location_id" in vals:
            self.env.registry.clear_cache()
        return result

    @ormcache()
    def _get_trip_vehicle_location_paths(self) -> tuple:
        self.flush_model(["trip_vehicle_id", "parent_path"])
        rows = self.env.execute_query(
            SQL(
                "SELECT parent_path FROM stock_location "
                "WHERE trip_vehicle_id IS NOT NULL"
            )
        )
        return tuple(path for (path,) in rows)

    def _has_trip_vehicle_descendant(self) -> bool:
        self.check_singleton()
        prefix = self.parent_path
        return any(
            path != prefix and path.startswith(prefix)
            for path in self._get_trip_vehicle_location_paths()
        )

    _trip_vehicle_parent_uniq = models.UniqueIndex(
        "(trip_vehicle_id, location_id) WHERE trip_vehicle_id IS NOT NULL",
        "A vehicle has one location under each place it loads from.",
    )

    def _get_or_create_trip_vehicle_location(self, vehicle):
        """Return the location of ``vehicle`` under this one, creating it if needed.

        :param recordset vehicle: a ``resource.asset.vehicle``
        :return: the vehicle's child location of this location
        :rtype: recordset
        """
        self.check_singleton()
        location = self.search(
            [("trip_vehicle_id", "=", vehicle.id), ("location_id", "=", self.id)],
            limit=1,
        )
        if location:
            return location
        return self.with_privilege(
            "stock_fleet_trace.privilege_trip_trace_record",
            reason="a trip gives its vehicle a location",
        ).create(
            {
                "name": vehicle.license_plate or vehicle.name,
                "location_id": self.id,
                "usage": self.usage,
                "company_id": self.company_id.id,
                "trip_vehicle_id": vehicle.id,
            }
        )
