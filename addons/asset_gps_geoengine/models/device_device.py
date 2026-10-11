from odoo import api, fields, models


class DeviceDevice(models.Model):
    _inherit = "device.device"

    asset_name = fields.Char(
        related="asset_id.display_name",
        string="Vehicle",
    )
    operator_name = fields.Char(related="asset_operator_id.name")
    stay_place = fields.Char(
        string="Where",
        compute="_compute_stay",
        help="Where the vehicle is parked right now: the geofence and its "
        "client, or the place outside every geofence. Empty while moving.",
    )
    stay_since = fields.Datetime(
        string="Since",
        compute="_compute_stay",
        help="Parked: its arrival. Moving: when it left its last stop.",
    )
    stay_elapsed = fields.Char(
        string="For",
        compute="_compute_stay",
    )

    @api.depends(
        "asset_id",
        "asset_id.display_name",
        "asset_operator_id",
        "asset_operator_id.name",
        "asset_license_plate",
    )
    def _compute_map_labels(self) -> None:
        super()._compute_map_labels()
        for device in self.filtered("asset_id"):
            vehicle = device.asset_name or device.name
            plate = device.asset_license_plate
            if plate and plate.casefold() not in vehicle.casefold():
                vehicle = f"{vehicle} ({plate})"
            if device.operator_name:
                device.map_title = device.operator_name
                device.map_subtitle = vehicle
            else:
                device.map_title = vehicle
                device.map_subtitle = False

    def _compute_stay(self):
        stops = self.env["device.gps.stop"].search(
            [("device_id", "in", self.ids), ("kind", "=", "stop")],
            order="arrival desc",
        )
        last_stop = {}
        for stop in stops:
            last_stop.setdefault(stop.device_id.id, stop)
        now = fields.Datetime.now()
        for device in self:
            stop = last_stop.get(device.id)
            place = since = False
            if device.gps_movement_state:
                if stop and stop.departure:
                    since = stop.departure
            elif stop and stop.ongoing:
                place = stop.place
                since = stop.arrival
            device.stay_place = place
            device.stay_since = since
            device.stay_elapsed = _format_elapsed(now - since) if since else False


def _format_elapsed(delta):
    minutes = max(int(delta.total_seconds() // 60), 0)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min"
