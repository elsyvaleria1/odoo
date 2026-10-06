from odoo import api, models

from ..tools.google_reserve_iap import GoogleReserveIAP


class ResourceScheduleException(models.Model):
    _inherit = "resource.schedule.exception"

    @api.model
    def _on_schedule_changed(self, scopes) -> None:
        super()._on_schedule_changed(scopes)
        windows = self._get_google_reserve_windows(scopes)
        if not windows:
            return
        google_reserve_iap = GoogleReserveIAP()
        for appointment_type, (date_from, date_to) in windows.items():
            google_reserve_iap.update_availabilities(
                appointment_type, date_from, date_to
            )

    @api.model
    def _get_google_reserve_windows(self, scopes):
        scopes = [scope for scope in scopes if scope["resource_id"]]
        if not scopes:
            return {}
        resources = self.env["resource.resource"].search(
            [
                ("appointment_type_ids.google_reserve_enable", "=", "True"),
                ("id", "in", list({scope["resource_id"] for scope in scopes})),
            ]
        )
        resource_by_id = resources.grouped("id")
        windows = {}
        for scope in scopes:
            resource = resource_by_id.get(scope["resource_id"])
            if not resource:
                continue
            for appointment_type in resource.appointment_type_ids:
                date_from, date_to = windows.get(
                    appointment_type, (scope["date_from"], scope["date_to"])
                )
                windows[appointment_type] = (
                    min(date_from, scope["date_from"]),
                    max(date_to, scope["date_to"]),
                )
        return windows
