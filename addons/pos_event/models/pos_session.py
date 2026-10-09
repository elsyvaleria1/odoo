from odoo import api, models


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _get_model_names_to_load(self, config):
        models = super()._get_model_names_to_load(config)
        models += [
            "event.event.ticket",
            "event.event",
            "event.slot",
            "event.registration",
            "event.question",
            "event.question.answer",
            "event.registration.answer",
        ]
        return models
