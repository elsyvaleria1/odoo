import logging

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

from .mixin_mail_thread import (
    LEGACY_HASH_ENABLED,
    LEGACY_HASH_IDLE_DAYS,
    LEGACY_HASH_LAST_USED,
)

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class IrConfig_Parameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.autovacuum
    def _gc_portal_legacy_hash(self) -> None:
        settings = self.env.registry.settings
        if not settings.get_bool(self.env, LEGACY_HASH_ENABLED):
            return
        params = self.with_privilege(
            "portal.privilege_track_legacy_hash",
            reason="end the legacy portal link fallback once nothing uses it",
        )
        today = fields.Date.today()
        last_used = fields.Date.to_date(settings.get(self.env, LEGACY_HASH_LAST_USED))
        if not last_used:
            # enabled by hand without a date: the idle days count from today
            params.set_param(LEGACY_HASH_LAST_USED, fields.Date.to_string(today))
            return
        idle = (today - last_used).days
        _debug.logic("legacy_hash_idle", days=idle, limit=LEGACY_HASH_IDLE_DAYS)
        if idle < LEGACY_HASH_IDLE_DAYS:
            return
        params.set_param(LEGACY_HASH_ENABLED, "False")
        _logger.info(
            "Portal links signed with the bare database secret are refused from "
            "now on: none was used since %s",
            last_used,
        )
