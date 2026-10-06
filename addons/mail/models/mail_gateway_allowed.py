from typing import NamedTuple

from markupsafe import Markup

from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

LOOP_MINUTES_DEFAULT = 120
LOOP_THRESHOLD_DEFAULT = 20


class LoopLimits(NamedTuple):
    minutes: int
    threshold: int


class MailGatewayAllowed(models.Model):
    _name = "mail.gateway.allowed"
    _description = "Mail Gateway Allowed"

    email = fields.Char(
        string="Email Address",
        required=True,
    )
    email_normalized = fields.Char(
        string="Normalized Email",
        compute="_compute_email_normalized",
        store=True,
        index=True,
    )

    @api.depends("email")
    def _compute_email_normalized(self) -> None:
        for record in self:
            record.email_normalized = tools.email_normalize(record.email)

    @api.constrains("email")
    def _check_email_normalizes(self) -> None:
        for record in self:
            if not tools.email_normalize(record.email):
                _debug.logic(
                    "email_rejected", record=record.id, reason="not_normalizable"
                )
                raise ValidationError(
                    self.env._("Invalid email address “%s”", record.email)
                )

    @api.model
    def _get_loop_limits(self) -> LoopLimits:
        settings = self.env.registry.settings
        return LoopLimits(
            settings.get_int(
                self.env, "mail.gateway.loop.minutes", LOOP_MINUTES_DEFAULT
            ),
            settings.get_int(
                self.env, "mail.gateway.loop.threshold", LOOP_THRESHOLD_DEFAULT
            ),
        )

    @api.model
    def get_empty_list_help(self, help_message: str) -> str:
        limits = self._get_loop_limits()
        return Markup(
            self.env._("""
            <p class="o_view_nocontent_smiling_face">
                Add addresses to the Allowed List
            </p><p>
                To protect you from spam and reply loops, Odoo automatically blocks emails
                coming to your gateway past a threshold of <b>%(threshold)i</b> emails every <b>%(minutes)i</b>
                minutes. If there are some addresses from which you need to receive very frequent
                updates, you can however add them below and Odoo will let them go through.
            </p>""")
        ) % {
            "threshold": limits.threshold,
            "minutes": limits.minutes,
        }
