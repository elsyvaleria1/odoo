from odoo import models


class AppointmentType(models.Model):
    _inherit = "appointment.type"

    def _slot_availability_prepare_resources_values(
        self, resources, start_dt_utc, end_dt_utc
    ):
        values = super()._slot_availability_prepare_resources_values(
            resources, start_dt_utc, end_dt_utc
        )
        values["resources_out_of_service"] = {
            resource.id
            for resource in resources.sudo()
            if not resource._accepts_bookings()
        }
        return values

    def _slot_availability_is_resource_available(
        self, slot, resource, availability_values
    ):
        out_of_service = availability_values.get("resources_out_of_service")
        if out_of_service is None:
            if not resource.sudo()._accepts_bookings():
                return False
        elif resource.id in out_of_service:
            return False
        return super()._slot_availability_is_resource_available(
            slot, resource, availability_values
        )
