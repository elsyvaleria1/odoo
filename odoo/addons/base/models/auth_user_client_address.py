import logging

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

from . import auth_user_client as clients

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class AuthUserClientAddress(models.Model):
    _name = "auth.user.client.address"
    _description = "Authentication Client Address"
    _order = "last_activity desc, id desc"
    _rec_name = "ip_address"
    _access_anchors = frozendict(
        {
            "owner": "client_id.user_id",
        }
    )

    client_id = fields.Many2one(
        comodel_name="auth.user.client",
        required=True,
        ondelete="cascade",
    )
    ip_address = fields.Char(string="IP Address")
    country = fields.Char()
    city = fields.Char()
    first_activity = fields.Datetime()
    last_activity = fields.Datetime()

    _device_address_uniq = models.UniqueIndex(
        "(client_id, ip_address) NULLS NOT DISTINCT"
    )

    @api.autovacuum
    def _gc_stale_addresses(self) -> tuple[int, bool] | None:
        cutoff = self.env["auth.user.client"]._retention_cutoff()
        if cutoff is None:
            _debug.logic("gc_stale_addresses_skipped", reason="retention_disabled")
            return None
        self.env.cr.execute(
            SQL(
                """
                DELETE FROM auth_user_client_address
                WHERE id IN (
                    SELECT address.id
                    FROM auth_user_client_address address
                    JOIN auth_user_client device ON device.id = address.client_id
                    WHERE address.last_activity < %s
                      AND address.ip_address IS DISTINCT FROM device.ip_address
                    ORDER BY address.id
                    LIMIT %s
                )
                """,
                cutoff,
                clients._RETENTION_BATCH,
            )
        )
        deleted = self.env.cr.rowcount
        _logger.info("GC stale device addresses delete %d entries", deleted)
        _debug.lifecycle("gc_stale_addresses", cutoff=str(cutoff), count=deleted)
        return deleted, deleted == clients._RETENTION_BATCH
