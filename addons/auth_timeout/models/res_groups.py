from odoo import api, fields, models
from odoo.tools import ormcache
from odoo.tools.date_utils import time_unit_selection

CACHE_INVALIDATE_FIELDS = (
    "lock_timeout",
    "lock_timeout_mfa",
    "lock_timeout_inactivity",
    "lock_timeout_inactivity_mfa",
)

MINUTES_PER_UNIT = {"day": 1440, "hour": 60, "minute": 1}


def human_readable_delay(minutes) -> tuple:
    for unit, size in MINUTES_PER_UNIT.items():
        if minutes and minutes % size == 0:
            return minutes // size, unit
    return minutes, "minute"


def human_readable_delay_to_minutes(delay, unit):
    return delay * MINUTES_PER_UNIT.get(unit, 1)


DELAY_UNITS = [
    (unit, label.lower())
    for unit, label in time_unit_selection("minute", "hour", "day")
]


class ResGroups(models.Model):
    _inherit = "res.groups"

    lock_timeout = fields.Integer(
        string="Session timeout",
        help="Time interval (in minutes) after which re-authentication is required, regardless of inactivity.",
    )

    lock_timeout_mfa = fields.Boolean(
        string="Require MFA on session timeout",
        help="Enable two-factor authentication when the session timeout is reached.",
    )

    lock_timeout_inactivity = fields.Integer(
        string="Inactivity timeout",
        help="Time (in minutes) of user inactivity after which re-authentication is required.",
    )

    lock_timeout_inactivity_mfa = fields.Boolean(
        string="Require MFA on inactivity timeout",
        help="Enable two-factor authentication when the inactivity timeout is reached.",
    )

    has_lock_timeout = fields.Boolean(
        compute="_compute_has_lock_timeout",
        readonly=False,
        help="Requires re-authentication after the user's last connection",
    )
    lock_timeout_delay_unit = fields.Selection(
        selection=DELAY_UNITS,
        compute="_compute_lock_timeout_delay_unit",
        readonly=False,
    )
    lock_timeout_delay_in_unit = fields.Integer(
        compute="_compute_lock_timeout_delay_unit",
        readonly=False,
    )
    lock_timeout_2fa_selection = fields.Selection(
        selection=[
            ("without_2fa", "Logout"),
            ("with_2fa", "Logout with two-factor authentication"),
        ],
        compute="_compute_lock_timeout_2fa_selection",
        inverse="_inverse_lock_timeout_2fa_selection",
    )

    has_lock_timeout_inactivity = fields.Boolean(
        compute="_compute_lock_timeout_inactivity_bool",
        readonly=False,
        help="Requires re-authentication after a period of user inactivity",
    )
    lock_timeout_inactivity_delay_unit = fields.Selection(
        selection=DELAY_UNITS,
        compute="_compute_lock_timeout_inactivity_delay_unit",
        readonly=False,
    )
    lock_timeout_inactivity_delay_in_unit = fields.Integer(
        compute="_compute_lock_timeout_inactivity_delay_unit",
        readonly=False,
    )
    lock_timeout_inactivity_2fa_selection = fields.Selection(
        selection=[
            ("without_2fa", "Screen lock"),
            ("with_2fa", "Screen lock with two-factor authentication"),
        ],
        compute="_compute_lock_timeout_inactivity_2fa_selection",
        inverse="_inverse_lock_timeout_inactivity_2fa_selection",
    )

    @api.depends("lock_timeout")
    def _compute_has_lock_timeout(self) -> None:
        for group in self:
            group.has_lock_timeout = bool(group.lock_timeout)

    @api.depends("lock_timeout")
    def _compute_lock_timeout_delay_unit(self) -> None:
        for group in self:
            (
                group.lock_timeout_delay_in_unit,
                group.lock_timeout_delay_unit,
            ) = human_readable_delay(group.lock_timeout)

    @api.depends("lock_timeout_mfa")
    def _compute_lock_timeout_2fa_selection(self) -> None:
        for group in self:
            group.lock_timeout_2fa_selection = (
                "with_2fa" if group.lock_timeout_mfa else "without_2fa"
            )

    def _inverse_lock_timeout_2fa_selection(self) -> None:
        for group in self:
            group.lock_timeout_mfa = group.lock_timeout_2fa_selection == "with_2fa"

    @api.depends("lock_timeout_inactivity")
    def _compute_lock_timeout_inactivity_bool(self) -> None:
        for group in self:
            group.has_lock_timeout_inactivity = bool(group.lock_timeout_inactivity)

    @api.depends("lock_timeout_inactivity")
    def _compute_lock_timeout_inactivity_delay_unit(self) -> None:
        for group in self:
            (
                group.lock_timeout_inactivity_delay_in_unit,
                group.lock_timeout_inactivity_delay_unit,
            ) = human_readable_delay(group.lock_timeout_inactivity)

    @api.depends("lock_timeout_inactivity_mfa")
    def _compute_lock_timeout_inactivity_2fa_selection(self) -> None:
        for group in self:
            group.lock_timeout_inactivity_2fa_selection = (
                "with_2fa" if group.lock_timeout_inactivity_mfa else "without_2fa"
            )

    def _inverse_lock_timeout_inactivity_2fa_selection(self) -> None:
        for group in self:
            group.lock_timeout_inactivity_mfa = (
                group.lock_timeout_inactivity_2fa_selection == "with_2fa"
            )

    @api.onchange("has_lock_timeout")
    def _onchange_has_lock_timeout(self) -> None:
        for group in self:
            if not group.has_lock_timeout:
                group.lock_timeout = False
                group.lock_timeout_mfa = False
            else:
                group.lock_timeout = 1440
                group.lock_timeout_mfa = True

    @api.onchange("lock_timeout_delay_unit", "lock_timeout_delay_in_unit")
    def _onchange_lock_timeout_delay_unit(self) -> None:
        for group in self:
            group.lock_timeout = human_readable_delay_to_minutes(
                group.lock_timeout_delay_in_unit,
                group.lock_timeout_delay_unit,
            )

    @api.onchange("has_lock_timeout_inactivity")
    def _onchange_has_lock_timeout_inactivity(self) -> None:
        for group in self:
            if not group.has_lock_timeout_inactivity:
                group.lock_timeout_inactivity = False
                group.lock_timeout_inactivity_mfa = False
            else:
                group.lock_timeout_inactivity = 15
                group.lock_timeout_inactivity_mfa = False

    @api.onchange(
        "lock_timeout_inactivity_delay_unit", "lock_timeout_inactivity_delay_in_unit"
    )
    def _onchange_lock_timeout_inactivity_delay_unit(self) -> None:
        for group in self:
            group.lock_timeout_inactivity = human_readable_delay_to_minutes(
                group.lock_timeout_inactivity_delay_in_unit,
                group.lock_timeout_inactivity_delay_unit,
            )

    @api.model_create_multi
    def create(self, vals_list):
        if any(
            field in vals for vals in vals_list for field in CACHE_INVALIDATE_FIELDS
        ):
            self.env.registry.clear_cache()
        return super().create(vals_list)

    def write(self, vals):
        if any(field in vals for field in CACHE_INVALIDATE_FIELDS):
            self.env.registry.clear_cache()
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda r: any(r[field] for field in CACHE_INVALIDATE_FIELDS)):
            self.env.registry.clear_cache()
        return super().unlink()

    @ormcache("self._ids")
    def _get_lock_timeouts(self):
        result = {}

        for key, mfa_key in [
            ("lock_timeout", "lock_timeout_mfa"),
            ("lock_timeout_inactivity", "lock_timeout_inactivity_mfa"),
        ]:
            values = [
                (g[key], g[mfa_key])
                for g in self.with_context({}).all_implied_ids
                if g[key]
            ]
            min_non_mfa = min(
                (timeout for timeout, mfa in values if not mfa), default=None
            )
            min_mfa = min((timeout for timeout, mfa in values if mfa), default=None)

            result[key] = []

            if min_mfa:
                result[key].append((min_mfa * 60, True))
            if min_non_mfa and (not min_mfa or min_non_mfa < min_mfa):
                result[key].append((min_non_mfa * 60, False))

            result[key].sort()

        return result
