import logging
from collections.abc import Collection
from datetime import timedelta
from itertools import batched

from odoo import api, fields, models
from odoo.http import get_session_max_inactivity, root
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

from . import auth_user_client as clients
from .auth_user_client import _current_client_id

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class AuthUserClientSession(models.Model):
    _name = "auth.user.client.session"
    _description = "Authentication Client Session"
    _order = "last_activity desc, id desc"
    _rec_name = "first_activity"

    client_id = fields.Many2one(
        comodel_name="auth.user.client",
        index=True,
        required=True,
        ondelete="cascade",
    )
    session_identifier = fields.Char(
        index="btree",
        required=True,
    )
    first_activity = fields.Datetime()
    last_activity = fields.Datetime()
    ended_at = fields.Datetime(readonly=True)
    end_reason = fields.Selection(
        selection=[
            ("revoked", "Revoked"),
            ("logout", "Logged Out"),
            ("expired", "Expired"),
            ("rotated", "Rotated"),
            ("legacy", "Legacy Binding"),
        ],
        readonly=True,
    )
    active = fields.Boolean(
        default=True,
        help="Unset once the session no longer exists: revoked, logged out or expired.",
    )

    _device_session_uniq = models.UniqueIndex("(session_identifier) WHERE active")

    @api.model
    def _mark_revoked(
        self,
        session_identifiers: Collection[str],
        device_ids: Collection[int] = (),
        *,
        reason: str = "revoked",
    ) -> int:
        identifiers = list(session_identifiers)
        devices = set(device_ids)
        if not identifiers and not devices:
            return 0
        self.env["auth.user.client"].flush_model(["active"])
        self.flush_model(["session_identifier", "active"])
        self.env.cr.execute(
            SQL(
                "UPDATE auth_user_client AS client SET active = client.active "
                "FROM (SELECT c.id FROM auth_user_client c "
                "WHERE c.id = ANY(%s) OR EXISTS ("
                "SELECT 1 FROM auth_user_client_session s WHERE s.client_id = c.id "
                "AND s.active AND s.session_identifier = ANY(%s)) "
                "ORDER BY c.id FOR UPDATE) AS locked WHERE client.id = locked.id",
                sorted(devices),
                identifiers,
            )
        )
        uid, now = self.env.uid, self.env.cr.now()
        revoked = 0
        if identifiers:
            self.env.cr.execute(
                SQL(
                    """
                    UPDATE auth_user_client_session AS s
                    SET active = FALSE, write_uid = %s, write_date = %s,
                        ended_at = %s, end_reason = %s
                    FROM auth_user_client AS c
                    WHERE s.session_identifier = ANY(%s) AND s.active AND c.id = s.client_id
                    RETURNING s.id, s.client_id, c.user_id
                    """,
                    uid,
                    now,
                    now,
                    reason,
                    identifiers,
                )
            )
            revoked = self.env.cr.rowcount
            ended = self.env.cr.fetchall()
            devices.update(client_id for _, client_id, _ in ended)
            if reason in {"revoked", "logout"}:
                self.env["auth.event"]._append(
                    [
                        {
                            "event": "session_logged_out"
                            if reason == "logout"
                            else "session_revoked",
                            "subject_user_id": user_id,
                            "client_ref": client_id,
                            "session_ref": session_id,
                        }
                        for session_id, client_id, user_id in ended
                    ]
                )
        if devices:
            self.env.cr.execute(
                SQL(
                    """
                    UPDATE auth_user_client device
                    SET active = FALSE, write_uid = %s, write_date = %s
                    WHERE device.id = ANY(%s)
                      AND device.active
                      AND NOT EXISTS (
                          SELECT 1
                          FROM auth_user_client_session live
                          WHERE live.client_id = device.id AND live.active
                      )
                    """,
                    uid,
                    now,
                    sorted(devices),
                )
            )
        self.invalidate_model(
            ["active", "ended_at", "end_reason", "write_uid", "write_date"]
        )
        self.env["auth.user.client"].invalidate_model(
            ["active", "write_uid", "write_date"]
        )
        _debug.lifecycle("sessions_revoked", sessions=revoked, devices=len(devices))
        return revoked

    @api.model
    def _follow_rotation(self, retired: str, successor: str) -> None:
        uid, now = self.env.uid, self.env.cr.now()
        client_id = _current_client_id()
        self.env["auth.user.client"].flush_model(["active"])
        self.env.cr.execute(
            SQL("UPDATE auth_user_client SET active = active WHERE id = %s", client_id)
        )
        self.flush_model(["session_identifier", "client_id"])
        self.env.cr.execute(
            SQL(
                """
            UPDATE auth_user_client_session SET
                session_identifier = %s, write_uid = %s, write_date = %s
            WHERE client_id = %s AND session_identifier = %s AND active
            """,
                successor,
                uid,
                now,
                client_id,
                retired,
            )
        )
        followed = self.env.cr.rowcount
        self.invalidate_model(["session_identifier", "write_uid", "write_date"])
        self.env["auth.user.client"].invalidate_model(
            ["recognition_key_hash", "write_uid", "write_date"]
        )
        ended = self._mark_revoked([retired], reason="rotated")
        _debug.lifecycle("session_rotation_followed", followed=followed, ended=ended)

    @api.model
    def _mark_logged_out(self, session_identifier: str) -> None:
        if self.env.cr.readonly:
            _debug.logic("sessions_logged_out_deferred", reason="readonly_cursor")
            return
        ended = self._mark_revoked([session_identifier], reason="logout")
        _debug.lifecycle("sessions_logged_out", uid=self.env.uid, sessions=ended)

    @api.autovacuum
    def _update_revoked(self) -> tuple[int, bool]:
        inactive_since = fields.Datetime.now() - timedelta(
            seconds=get_session_max_inactivity(self.env)
        )
        self.env.cr.execute(
            SQL(
                """
                SELECT DISTINCT session_identifier
                FROM auth_user_client_session
                WHERE active AND last_activity < %s
                """,
                inactive_since,
            )
        )
        candidates = [identifier for (identifier,) in self.env.cr.fetchall()]
        _debug.pipeline("revoke_sweep_start", candidates=len(candidates))
        revoked = 0
        for batch in batched(candidates, clients._REVOKE_SWEEP_BATCH, strict=False):
            missing = root.session_store.get_missing_session_identifiers(batch)
            _debug.pipeline(
                "revoke_sweep", candidates=len(batch), missing_sessions=len(missing)
            )
            if not missing:
                continue
            count = self._mark_revoked(missing, reason="expired")
            revoked += count
            _debug.lifecycle("sessions_revoked", count=count, by="gc")
            if not self.env["ir.cron"]._commit_progress(count):
                _debug.logic("revoke_sweep_stopped", reason="time_budget")
                return revoked, True
        _debug.lifecycle("revoke_sweep_done", revoked=revoked)
        return revoked, False

    @api.autovacuum
    def _gc_ended_sessions(self) -> tuple[int, bool] | None:
        cutoff = self.env["auth.user.client"]._retention_cutoff()
        if cutoff is None:
            _debug.logic("gc_ended_sessions_skipped", reason="retention_disabled")
            return None
        self.env.cr.execute(
            SQL(
                """
                DELETE FROM auth_user_client_session
                WHERE id IN (
                    SELECT id
                    FROM auth_user_client_session
                    WHERE active IS NOT TRUE
                      AND (COALESCE(ended_at, last_activity) IS NULL
                           OR COALESCE(ended_at, last_activity) < %s)
                    ORDER BY id
                    LIMIT %s
                )
                """,
                cutoff,
                clients._RETENTION_BATCH,
            )
        )
        deleted = self.env.cr.rowcount
        _logger.info("GC ended device sessions delete %d entries", deleted)
        _debug.lifecycle("gc_ended_sessions", cutoff=str(cutoff), count=deleted)
        return deleted, deleted == clients._RETENTION_BATCH
