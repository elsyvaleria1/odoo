from odoo import api, models

from .hr_leave import LEAVE_TO_DEFER_ACTIVITY_XMLID


class MailActivityType(models.Model):
    _inherit = "mail.activity.type"

    @api.model
    def _get_model_info_by_xmlid(self):
        info = super()._get_model_info_by_xmlid()
        info[LEAVE_TO_DEFER_ACTIVITY_XMLID] = {
            "res_model": "hr.leave",
            "unlink": False,
        }
        return info
