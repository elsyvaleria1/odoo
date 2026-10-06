import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger(__name__)

_debug = DebugLog(__name__)


class WizardIrProfileEnable(models.TransientModel):
    _name = "wizard.ir.profile.enable"
    _description = "Enable profiling for some time"

    duration = fields.Selection(
        selection=[
            ("minutes_5", "5 Minutes"),
            ("hours_1", "1 Hour"),
            ("days_1", "1 Day"),
            ("months_1", "1 Month"),
        ],
        string="Enable profiling for",
    )
    expiration = fields.Datetime(
        string="Enable profiling until",
        compute="_compute_expiration",
        store=True,
        readonly=False,
    )

    @api.depends("duration")
    def _compute_expiration(self) -> None:
        for record in self:
            unit, quantity = (record.duration or "days_0").split("_")
            record.expiration = fields.Datetime.now() + relativedelta(
                **{unit: int(quantity)}
            )

    def submit(self) -> bool:
        _debug.lifecycle(
            "profiling_enabled_until", uid=self.env.uid, until=str(self.expiration)
        )
        self.env["ir.config_parameter"].set_param(
            "base.profiling_enabled_until", self.expiration
        )
        return False
