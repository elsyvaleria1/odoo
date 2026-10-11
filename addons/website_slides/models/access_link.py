from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

from .slide_channel_partner import INVITATION_VALIDITY_MONTHS


class AccessLink(models.Model):
    _inherit = "access.link"

    cause = fields.Selection(
        selection_add=[("invitation", "Course invitation")],
        ondelete={"invitation": "cascade"},
    )

    @api.model
    def _get_cause_lifetimes(self) -> dict[str, timedelta | relativedelta]:
        return super()._get_cause_lifetimes() | {
            "invitation": relativedelta(months=INVITATION_VALIDITY_MONTHS)
        }
