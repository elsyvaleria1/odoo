from itertools import batched
from typing import Any, Self
from uuid import uuid4

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

_debug = DebugLog(__name__)

RETENTION_DAYS_DEFAULT = 365
EXPIRY_BATCH_SIZE = 5000


class AuthEvent(models.Model):
    _name = "auth.event"
    _description = "Authentication Event"
    _order = "id desc"
    _rec_name = "event"
    _log_access = False
    _allow_sudo_commands = False
    _access_anchors = frozendict(
        {"owner": "subject_user_id", "company": "subject_user_id.company_ids"}
    )

    event = fields.Selection(
        selection=[
            ("client_revoked", "Client sessions revoked"),
            ("session_revoked", "Session revoked"),
            ("session_logged_out", "Session logged out"),
            ("other_sessions_ended", "Other user sessions ended"),
            ("credential_issued", "Credential issued"),
            ("credential_revoked", "Credential revoked"),
        ],
        index=True,
        readonly=True,
        required=True,
    )
    occurred_at = fields.Datetime(
        readonly=True,
        required=True,
    )
    actor_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        ondelete="set null",
    )
    subject_user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        readonly=True,
        ondelete="set null",
    )
    actor_ref = fields.Integer(readonly=True)
    subject_user_ref = fields.Integer(
        readonly=True,
        required=True,
    )
    client_ref = fields.Integer(readonly=True)
    session_ref = fields.Integer(readonly=True)
    model_name = fields.Char(readonly=True)
    credential_ref = fields.Integer(readonly=True)
    generation = fields.Integer(readonly=True)
    correlation_id = fields.Char(
        index=True,
        readonly=True,
        required=True,
    )

    _occurred_at_idx = models.Index("(occurred_at, id)")

    @api.model
    def _append(self, values: list[ValuesType]) -> Self:
        if not values:
            return self.browse()
        correlation_id = str(uuid4())
        now = self.env.cr.now()
        allowed = {
            "event",
            "subject_user_id",
            "client_ref",
            "session_ref",
            "model_name",
            "credential_ref",
            "generation",
        }
        rows = []
        for vals in values:
            if vals.keys() - allowed:
                raise ValueError("Unsupported authentication event field")
            event = self._fields["event"].convert_to_cache(vals["event"], self)
            rows.append(
                SQL(
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    event,
                    now,
                    self.env.uid,
                    vals["subject_user_id"],
                    self.env.uid,
                    vals["subject_user_id"],
                    vals.get("client_ref"),
                    vals.get("session_ref"),
                    vals.get("model_name"),
                    vals.get("credential_ref"),
                    vals.get("generation"),
                    correlation_id,
                )
            )
        event_ids = []
        for batch in batched(rows, 1000, strict=False):
            self.env.cr.execute(
                SQL(
                    "INSERT INTO auth_event (event, occurred_at, actor_id, subject_user_id, "
                    "actor_ref, subject_user_ref, client_ref, session_ref, model_name, "
                    "credential_ref, generation, correlation_id) VALUES %s RETURNING id",
                    SQL(", ").join(batch),
                )
            )
            event_ids.extend(row[0] for row in self.env.cr.fetchall())
        events = self.browse(event_ids)
        _debug.lifecycle("events_appended", count=len(events))
        return events

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if vals_list:
            raise AccessError(
                self.env._("Authentication events are written by security actions.")
            )
        return super().create(vals_list)

    def write(self, vals: dict[str, Any]) -> bool:
        if not self:
            return True
        raise AccessError(self.env._("Authentication events cannot be changed."))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_retention(self) -> None:
        raise AccessError(
            self.env._(
                "Authentication events expire only through their retention policy."
            )
        )

    @api.autovacuum
    def _gc_events(self) -> tuple[int, bool]:
        days = self.env["ir.config_parameter"].get_param_int(
            "auth.event_retention_days", RETENTION_DAYS_DEFAULT
        )
        if days <= 0:
            return 0, False
        self.env.cr.execute(
            SQL(
                "DELETE FROM auth_event WHERE id IN ("
                "SELECT id FROM auth_event WHERE occurred_at < "
                "(now() at time zone 'UTC') - %s * interval '1 day' "
                "ORDER BY occurred_at, id LIMIT %s)",
                days,
                EXPIRY_BATCH_SIZE,
            )
        )
        count = self.env.cr.rowcount
        _debug.lifecycle("events_expired", count=count, retention_days=days)
        return count, count == EXPIRY_BATCH_SIZE
