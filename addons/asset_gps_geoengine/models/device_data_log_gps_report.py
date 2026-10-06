from odoo import models


class DeviceGpsLogReport(models.Model):
    _inherit = "device.data.log.gps.report"

    def _rolling_mark_stale(self):
        super()._rolling_mark_stale()
        # Stops are stored too; their normal trailing refresh cannot repair
        # settled dates after a resource timezone or tracker target changes.
        self.env["device.gps.stop"]._mark_dates_stale()
