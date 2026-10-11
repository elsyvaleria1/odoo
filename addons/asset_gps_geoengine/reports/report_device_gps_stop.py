from itertools import groupby

from odoo import api, models


class ReportDeviceGpsStop(models.AbstractModel):

    _name = "report.asset_gps_geoengine.report_device_gps_stop"
    _description = "Vehicle Stops Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        stops = self.env["device.gps.stop"].browse(docids)
        stops = stops.sorted(
            lambda s: (
                s.date,
                s.asset_id.display_name or s.device_id.name or "",
                s.arrival or s.last_seen or s.create_date,
            )
        )
        sections = [
            {
                "date": date,
                "device": device,
                "stops": self.env["device.gps.stop"].union(*rows),
            }
            for (date, device), rows in groupby(
                stops, key=lambda s: (s.date, s.device_id)
            )
        ]
        return {
            "doc_ids": docids,
            "doc_model": "device.gps.stop",
            "docs": stops,
            "sections": sections,
        }
