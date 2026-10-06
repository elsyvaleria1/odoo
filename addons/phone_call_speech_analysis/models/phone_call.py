from odoo import models


class PhoneCall(models.Model):
    _name = "phone.call"
    _inherit = ["mixin.speech.analysis", "phone.call"]

    def _speech_analysis_ready(self) -> bool:
        return bool(self.end_date)
