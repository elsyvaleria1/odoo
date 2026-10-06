from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class EventTrack(models.Model):
    _inherit = "event.track"

    def action_unschedule(self):
        self.check_singleton()
        _debug.lifecycle("track_unscheduled", track=self, was=self.date)
        self.date = None
        self.date_end = None
        return {"type": "ir.actions.act_window_close"}
