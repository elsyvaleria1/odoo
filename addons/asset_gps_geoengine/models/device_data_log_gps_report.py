from odoo import models


class DeviceGpsLogReport(models.Model):
    _inherit = "device.data.log.gps.report"

    def _rolling_mark_stale(self):
        super()._rolling_mark_stale()
        self.env["device.gps.stop"]._mark_dates_stale()
