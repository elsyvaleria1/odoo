from datetime import timedelta

from odoo import api, fields, models

from .stock_picking_batch import HARSH_DRIVING_EVENT

INCIDENT_EVENT_WINDOW = timedelta(minutes=15)


class StockTripIncident(models.Model):
    _inherit = "stock.trip.incident"

    gps_note = fields.Text(
        string="GPS Around the Incident",
        readonly=True,
        help="Harsh driving the vehicle's GPS reported close to the incident.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        incidents = super().create(vals_list)
        for incident in incidents.with_privilege(
            "stock_fleet_trace_gps.privilege_trip_gps_read",
            reason="an incident is placed where the vehicle's track was",
        ):
            incident._update_from_gps()
        return incidents

    def _update_from_gps(self) -> None:
        self.check_singleton()
        vehicle = self.batch_id.vehicle_id
        if not vehicle.resource_id._gps_device_ids():
            return
        position = vehicle.resource_id._gps_position(self.date)
        vals = {}
        if position and not (self.latitude or self.longitude):
            vals.update(latitude=position.latitude, longitude=position.longitude)
            if not self.odometer:
                vals["odometer"] = vehicle.resource_id._gps_odometer_at(self.date)
        harsh = self.env["device.data.log.gps"].search(
            [
                *vehicle.resource_id._gps_observation_domain(),
                ("timestamp", ">=", self.date - INCIDENT_EVENT_WINDOW),
                ("timestamp", "<=", self.date + INCIDENT_EVENT_WINDOW),
                ("event_type", "=", HARSH_DRIVING_EVENT),
            ]
        )
        if harsh:
            vals["gps_note"] = "\n".join(
                self.env._(
                    "Harsh driving at %(time)s, %(speed)s km/h",
                    time=fields.Datetime.to_string(log.timestamp),
                    speed=round(log.speed or 0),
                )
                for log in harsh
            )
        if vals:
            self.write(vals)
