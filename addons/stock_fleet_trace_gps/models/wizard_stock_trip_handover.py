from odoo import api, models
from odoo.exceptions import UserError


class WizardStockTripHandover(models.TransientModel):
    _inherit = "wizard.stock.trip.handover"

    @api.onchange("vehicle_id")
    def _onchange_vehicle_id_gps_readings(self) -> None:
        # A rescue vehicle with GPS departs with the readings of its own track,
        # so its return cannot contradict a number typed from memory.
        vehicle = self.vehicle_id.resource_id.with_privilege(
            "stock_fleet_trace_gps.privilege_trip_gps_read",
            reason="a handover reads the rescue vehicle's current readings",
        )
        if not vehicle.gps_device_id:
            return
        try:
            self.odometer_departure = vehicle.get_current_odometer()
        except UserError:
            return
        fuel = vehicle.get_current_fuel_percentage()
        if fuel:
            self.fuel_departure = fuel
