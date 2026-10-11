import hashlib
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Self

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Field
from odoo.http import (
    STORED_SESSION_BYTES,
    GeoIP,
    request,
    root,
)
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

from .res_users import check_identity

if TYPE_CHECKING:
    from odoo.db import BaseCursor

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

_MOBILE_PLATFORMS = frozenset(
    {"android", "iphone", "ipad", "blackberry", "symbian", "windows phone"}
)

_DISPLAY_NAMES = {
    "blackberry": "BlackBerry",
    "chromeos": "ChromeOS",
    "freebsd": "FreeBSD",
    "ipad": "iPad",
    "iphone": "iPhone",
    "macos": "macOS",
    "msie": "Internet Explorer",
    "netbsd": "NetBSD",
    "openbsd": "OpenBSD",
    "samsung": "Samsung Internet",
}

CLIENT_KEY_COOKIE = "device_key"
_CLIENT_KEY_MAX_AGE = 400 * 24 * 60 * 60
_CLIENT_KEY_RE = re.compile(r"[A-Za-z0-9_-]{43}")

DEFAULT_RETENTION_DAYS = 90
_REVOKE_SWEEP_BATCH = 10_000
_RETENTION_BATCH = 10_000

_USER_WRITABLE_FIELDS = frozenset({"name"})


def _platform_type(platform: str | None) -> str:
    if not platform:
        return "unknown"
    return "mobile" if platform.lower() in _MOBILE_PLATFORMS else "computer"


def _display(name: str) -> str:
    return _DISPLAY_NAMES.get(name) or name.title()


def _utc_naive(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=UTC).replace(tzinfo=None)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _browser_key(req: Any, *, issue: bool) -> str | None:
    key = getattr(req, "device_key", None) or req.httprequest.cookies.get(
        CLIENT_KEY_COOKIE
    )
    if key and _CLIENT_KEY_RE.fullmatch(key):
        return key
    future_response = getattr(req, "future_response", None)
    if not issue or future_response is None:
        return None
    key = secrets.token_urlsafe(32)
    future_response.set_cookie(
        CLIENT_KEY_COOKIE, key, max_age=_CLIENT_KEY_MAX_AGE, httponly=True
    )
    req.device_key = key
    _debug.lifecycle("device_key_issued")
    return key


def _device_key_hash(
    key: str | None,
    session_identifier: str,
    platform: str | None,
    browser: str | None,
) -> str:
    if key:
        return _sha256(key)
    return _sha256(
        "\x1f".join(("session", session_identifier, platform or "", browser or ""))
    )


def _current_client_id() -> int | None:
    return request.session.get("auth_client_id") if request else None


class AuthUserClient(models.Model):
    _name = "auth.user.client"
    _description = "Authentication Client"
    _order = "last_activity desc, id desc"
    _rec_names_search = ["name", "platform", "browser"]
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    user_id = fields.Many2one(
        comodel_name="res.users",
        required=True,
        ondelete="cascade",
    )
    recognition_key_hash = fields.Char(
        copy=False,
        readonly=True,
        required=True,
    )
    recognition_method = fields.Selection(
        selection=[
            ("cookie", "Recognition Cookie"),
            ("session", "Session"),
            ("legacy", "Legacy (Unclassified)"),
        ],
        default="session",
        readonly=True,
        required=True,
    )
    session_generation = fields.Integer(
        default=0,
        readonly=True,
        required=True,
    )
    name = fields.Char(
        string="Device Name",
        help="A name of your choosing, shown instead of the platform and browser.",
    )
    platform = fields.Char()
    browser = fields.Char()
    platform_type = fields.Selection(
        selection=[
            ("computer", "Computer"),
            ("mobile", "Mobile"),
            ("unknown", "Unknown"),
        ]
    )
    ip_address = fields.Char(string="IP Address")
    country = fields.Char()
    city = fields.Char()
    first_activity = fields.Datetime()
    last_activity = fields.Datetime(index="btree")
    active = fields.Boolean(
        default=True,
        help="Unset once none of the device's sessions exists any more.",
    )
    session_ids = fields.One2many(
        comodel_name="auth.user.client.session",
        inverse_name="client_id",
        string="Sessions",
    )
    address_ids = fields.One2many(
        comodel_name="auth.user.client.address",
        inverse_name="client_id",
        string="Addresses",
    )
    is_current = fields.Boolean(
        string="Current Device",
        compute="_compute_is_current",
        order_by_sql="_order_by_sql_is_current",
    )

    _identity_uniq = models.UniqueIndex("(user_id, recognition_key_hash)")

    @api.depends("name", "platform", "browser")
    def _compute_display_name(self) -> None:
        for device in self:
            if device.name:
                device.display_name = device.name
                continue
            unknown = self.env._("Unknown")
            platform = _display(device.platform) if device.platform else unknown
            browser = _display(device.browser) if device.browser else unknown
            device.display_name = f"{platform} {browser}"

    @api.depends_context("uid")
    def _compute_is_current(self) -> None:
        current = _current_client_id()
        for device in self:
            device.is_current = current is not None and device.id == current

    def _order_by_sql_is_current(
        self, field: Field, alias: str, direction: Any, nulls: Any, query: Any
    ) -> SQL:
        current = _current_client_id()
        if current is None:
            return SQL.EMPTY
        _debug.logic("order_by_is_current", direction=str(direction))
        return SQL("%s = %s %s", SQL.identifier(alias, "id"), current, direction)

    def write(self, vals: dict[str, Any]) -> bool:
        if not (self.env.su or self.env.is_system()) and (
            set(vals) - _USER_WRITABLE_FIELDS
        ):
            _debug.logic("device_write_refused", uid=self.env.uid, fields=sorted(vals))
            raise AccessError(self.env._("You can only rename a device."))
        return super().write(vals)

    def action_archive(self) -> dict[str, Any] | None:
        return self.revoke()

    def action_unarchive(self) -> None:
        raise UserError(
            self.env._(
                "A revoked device cannot be restored: it comes back by itself "
                "when its browser signs in again."
            )
        )

    def action_rename(self) -> dict[str, Any]:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Rename Device"),
            "res_model": "auth.user.client",
            "res_id": self.id,
            "views": [(self.env.ref("base.auth_user_client_view_rename").id, "form")],
            "target": "new",
        }

    @api.model
    @_debug.perf.timed
    def _bind_session(self, session: Any, req: Any = None) -> tuple[Self, bool]:
        uid = session.uid
        if not uid:
            raise AccessError(self.env._("An authenticated user is required."))
        key = _browser_key(req, issue=True) if req is not None else None
        identifier = session.sid[:STORED_SESSION_BYTES]
        recognition_hash = _device_key_hash(key, identifier, None, None)
        now = self.env.cr.now()
        self.env.cr.execute(
            SQL(
                """
            INSERT INTO auth_user_client AS client (
                user_id, recognition_key_hash, recognition_method,
                session_generation, active, first_activity, last_activity,
                create_uid, create_date, write_uid, write_date
            ) VALUES (%s, %s, %s, 0, TRUE, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, recognition_key_hash) DO UPDATE SET
                active = TRUE, recognition_method = EXCLUDED.recognition_method,
                write_uid = EXCLUDED.write_uid, write_date = EXCLUDED.write_date
            RETURNING id, session_generation, xmax = 0
            """,
                uid,
                recognition_hash,
                "cookie" if key else "session",
                now,
                now,
                uid,
                now,
                uid,
                now,
            )
        )
        client_id, generation, inserted = self.env.cr.fetchone()
        self.browse(client_id)._check_login_authority(session)
        self.env.cr.execute(
            SQL(
                """
            INSERT INTO auth_user_client_session (
                client_id, session_identifier, active, first_activity, last_activity,
                create_uid, create_date, write_uid, write_date
            ) VALUES (%s, %s, TRUE, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_identifier) WHERE active DO UPDATE SET
                active = TRUE, last_activity = EXCLUDED.last_activity
            WHERE auth_user_client_session.client_id = EXCLUDED.client_id
            RETURNING id
            """,
                client_id,
                identifier,
                now,
                now,
                uid,
                now,
                uid,
                now,
            )
        )
        if not self.env.cr.fetchone():
            raise AccessError(
                self.env._("The session is already bound to another client.")
            )
        self.env.cr.execute(
            SQL("SELECT COALESCE(session_epoch, 0) FROM res_users WHERE id = %s", uid)
        )
        (epoch,) = self.env.cr.fetchone()
        session.update(
            auth_client_id=client_id,
            auth_client_generation=generation,
            auth_user_epoch=epoch,
        )
        _debug.lifecycle(
            "session_bound",
            uid=uid,
            client_id=client_id,
            generation=generation,
            inserted=inserted,
        )
        return self.browse(client_id), inserted

    def _check_login_authority(self, session: Any) -> None:
        pass

    @api.model
    def _is_session_valid(
        self, session: Any, fresh_primary_cr: BaseCursor | None = None
    ) -> bool:
        client_id = session.get("auth_client_id")
        generation = session.get("auth_client_generation")
        epoch = session.get("auth_user_epoch")
        if not client_id or generation is None or epoch is None:
            _debug.logic("binding_refused", uid=session.uid, reason="missing_binding")
            return False
        if fresh_primary_cr is not None:
            valid = self._binding_is_current(
                fresh_primary_cr, session, client_id, generation, epoch
            )
        else:
            with self.env.registry.cursor(readonly=True, primary=True) as cr:
                valid = self._binding_is_current(
                    cr, session, client_id, generation, epoch
                )
        _debug.logic(
            "binding_checked",
            uid=session.uid,
            client_id=client_id,
            valid=valid,
            reason="current" if valid else "revoked_or_missing",
        )
        return valid

    @api.model
    def _binding_is_current(
        self,
        cr: BaseCursor,
        session: Any,
        client_id: int,
        generation: int,
        epoch: int,
    ) -> bool:
        with _debug.perf(
            "binding_validated", cr=cr, uid=session.uid, client_id=client_id
        ):
            cr.execute(
                SQL(
                    """
                SELECT 1 FROM auth_user_client client
                JOIN res_users usr ON usr.id = client.user_id
                WHERE client.id = %s AND client.user_id = %s
                  AND client.session_generation = %s AND client.active
                  AND COALESCE(usr.session_epoch, 0) = %s
                  AND (usr.active OR usr.id = %s)
                  AND EXISTS (SELECT 1 FROM auth_user_client_session s
                      WHERE s.client_id = client.id AND s.active
                        AND s.session_identifier = %s)
                """,
                    client_id,
                    session.uid,
                    generation,
                    epoch,
                    SUPERUSER_ID,
                    session.sid[:STORED_SESSION_BYTES],
                )
            )
            return bool(cr.fetchone())

    @api.model
    @_debug.perf.timed
    def _observe(self, request: Any) -> None:
        session = request.session
        client_id = session.get("auth_client_id")
        if not client_id:
            _debug.logic("observation_skipped", reason="unbound_session")
            return
        trace = session.update_trace(request)
        if not trace:
            _debug.logic("observation_skipped", reason="trace_unchanged")
            return
        geoip = GeoIP(trace["ip_address"], app=request.app)
        values = {
            "client_id": client_id,
            "uid": session.uid,
            "generation": session.get("auth_client_generation"),
            "identifier": session.sid[:STORED_SESSION_BYTES],
            "platform": trace["platform"],
            "browser": trace["browser"],
            "platform_type": _platform_type(trace["platform"]),
            "ip": trace["ip_address"],
            "country": geoip.get("country_name"),
            "city": geoip.get("city"),
            "first": _utc_naive(trace["first_activity"]),
            "last": _utc_naive(trace["last_activity"]),
            "now": self.env.cr.now(),
        }
        statement = SQL(
            """
            WITH observed AS (
                UPDATE auth_user_client AS c SET
                    platform = %(platform)s, browser = %(browser)s,
                    platform_type = %(platform_type)s,
                    ip_address = CASE WHEN c.last_activity > %(last)s
                        THEN c.ip_address ELSE %(ip)s END,
                    country = CASE WHEN c.last_activity > %(last)s
                        THEN c.country ELSE %(country)s END,
                    city = CASE WHEN c.last_activity > %(last)s
                        THEN c.city ELSE %(city)s END,
                    first_activity = LEAST(c.first_activity, %(first)s),
                    last_activity = GREATEST(c.last_activity, %(last)s),
                    write_uid = %(uid)s, write_date = %(now)s
                WHERE c.id = %(client_id)s AND c.user_id = %(uid)s AND c.active
                  AND c.session_generation = %(generation)s
                RETURNING c.id
            ), seen_session AS (
                UPDATE auth_user_client_session s SET
                    first_activity = LEAST(s.first_activity, %(first)s),
                    last_activity = GREATEST(s.last_activity, %(last)s)
                FROM observed c WHERE s.client_id = c.id
                  AND s.session_identifier = %(identifier)s AND s.active
            )
            INSERT INTO auth_user_client_address AS a (
                client_id, ip_address, country, city, first_activity, last_activity,
                create_uid, create_date, write_uid, write_date
            ) SELECT id, %(ip)s, %(country)s, %(city)s, %(first)s, %(last)s,
                     %(uid)s, %(now)s, %(uid)s, %(now)s FROM observed
            ON CONFLICT (client_id, ip_address) DO UPDATE SET
                country = CASE WHEN a.last_activity > EXCLUDED.last_activity
                    THEN a.country ELSE EXCLUDED.country END,
                city = CASE WHEN a.last_activity > EXCLUDED.last_activity
                    THEN a.city ELSE EXCLUDED.city END,
                first_activity = LEAST(a.first_activity, EXCLUDED.first_activity),
                last_activity = GREATEST(a.last_activity, EXCLUDED.last_activity),
                write_uid = EXCLUDED.write_uid, write_date = EXCLUDED.write_date
            """,
            **values,
        )
        if self.env.cr.readonly:
            registry = self.env.registry

            def record() -> None:
                with registry.cursor() as cr:
                    cr.execute(statement)

            request.call_after_release(record)
            _debug.lifecycle("client_observation_deferred", client_id=client_id)
            return
        with self.env.cr.savepoint(flush=False):
            self.env.cr.execute(statement)
        _debug.lifecycle("client_observed", uid=session.uid, client_id=client_id)

    @api.model
    def _probe_integrity(self, limit: int = 100) -> dict[str, Any]:
        if not self.env.is_system():
            raise AccessError(
                self.env._("Only administrators can inspect client integrity.")
            )
        limit = max(1, min(int(limit), 1000))
        has_sessions = SQL(
            "EXISTS (SELECT 1 FROM auth_user_client_session s "
            "WHERE s.client_id = c.id AND s.active)"
        )
        predicates = {
            "inactive_clients_with_active_sessions": SQL(
                "NOT c.active AND %s", has_sessions
            ),
            "active_clients_without_active_sessions": SQL(
                "c.active AND NOT %s", has_sessions
            ),
        }
        result: dict[str, Any] = {"truncated": False}
        with _debug.perf("client_integrity_probe", cr=self.env.cr, limit=limit):
            for reason, predicate in predicates.items():
                self.env.cr.execute(
                    SQL(
                        "SELECT c.id FROM auth_user_client c WHERE %s ORDER BY c.id LIMIT %s",
                        predicate,
                        limit + 1,
                    )
                )
                ids = [row[0] for row in self.env.cr.fetchall()]
                result[reason] = ids[:limit]
                result["truncated"] |= len(ids) > limit
        return result

    @check_identity
    def revoke(self) -> dict[str, Any] | None:
        if self._revoke():
            return {"type": "ir.actions.client", "tag": "reload"}
        return None

    def _revoke(self) -> bool:
        return self._end_sessions()

    def _end_sessions(self) -> bool:
        if not self:
            _debug.logic("revoke_skipped", uid=self.env.uid, reason="empty_recordset")
            return False
        if not self.env.is_system() and self.mapped("user_id") != self.env.user:
            _debug.logic("revoke_refused", uid=self.env.uid, devices=self.ids)
            raise AccessError(self.env._("You can only revoke your own devices."))
        self.flush_model(["session_generation", "active"])
        self.env.cr.execute(
            SQL(
                "UPDATE auth_user_client SET session_generation = session_generation + 1, "
                "active = FALSE WHERE id = ANY(%s)",
                self.ids,
            )
        )
        self.invalidate_recordset(["session_generation", "active"])
        self.env["auth.user.client.session"].flush_model(["client_id", "active"])
        self.env.cr.execute(
            SQL(
                """
                SELECT DISTINCT session_identifier
                FROM auth_user_client_session
                WHERE client_id = ANY(%s) AND active
                ORDER BY session_identifier
                """,
                self.ids,
            )
        )
        session_identifiers = [identifier for (identifier,) in self.env.cr.fetchall()]
        must_logout = any(self.mapped("is_current"))
        self._schedule_session_cleanup(session_identifiers)
        revoked = self.env["auth.user.client.session"]._mark_revoked(
            session_identifiers, self.ids
        )
        _logger.info(
            "User %d revokes %d device(s), %d session(s), of user(s) %s",
            self.env.uid,
            len(self),
            len(session_identifiers),
            self.mapped("user_id").ids,
        )
        _debug.lifecycle(
            "devices_revoked",
            uid=self.env.uid,
            devices=len(self),
            sessions=revoked,
            logout=must_logout,
        )
        self.env["auth.event"]._append(
            [
                {
                    "event": "client_revoked",
                    "subject_user_id": client.user_id.id,
                    "client_ref": client.id,
                    "generation": client.session_generation,
                }
                for client in self
            ]
        )
        if must_logout:
            request.session.logout()
        return must_logout

    @api.model
    def _schedule_session_cleanup(self, identifiers: list[str]) -> None:
        if not identifiers:
            return
        store = root.session_store
        identifiers = list(identifiers)

        def cleanup_sessions():
            try:
                store.remove_sessions_for_identifiers(identifiers)
            except Exception:
                _logger.warning(
                    "Session cleanup failed after client revocation", exc_info=True
                )
                _debug.logic("session_cleanup_deferred", sessions=len(identifiers))

        self.env.cr.postcommit.add(cleanup_sessions)

    def _notify_new_client(self) -> None:
        _debug.lifecycle("new_device", device=self.id, user=self.user_id.id)

    @api.autovacuum
    def _gc_revoked_clients(self) -> tuple[int, bool] | None:
        cutoff = self._retention_cutoff()
        if cutoff is None:
            _debug.logic("gc_revoked_devices_skipped", reason="retention_disabled")
            return None
        self.env.cr.execute(
            SQL(
                """
                DELETE FROM auth_user_client
                WHERE id IN (
                    SELECT id
                    FROM auth_user_client
                    WHERE active IS NOT TRUE
                      AND %s
                      AND (last_activity IS NULL OR last_activity < %s)
                    ORDER BY id
                    LIMIT %s
                )
                """,
                self._gc_retention_filter(cutoff),
                cutoff,
                _RETENTION_BATCH,
            )
        )
        deleted = self.env.cr.rowcount
        _logger.info("GC revoked devices delete %d entries", deleted)
        _debug.lifecycle("gc_revoked_devices", cutoff=str(cutoff), count=deleted)
        return deleted, deleted == _RETENTION_BATCH

    @api.model
    def _gc_retention_filter(self, cutoff):
        return SQL(
            "NOT EXISTS (SELECT 1 FROM auth_user_client_session s "
            "WHERE s.client_id = auth_user_client.id "
            "AND (s.active OR COALESCE(s.ended_at, s.last_activity) >= %s))",
            cutoff,
        )

    @api.model
    def _retention_cutoff(self) -> datetime | None:
        retention_days = self.env["ir.config_parameter"].get_param_int(
            "base.device_retention_days", DEFAULT_RETENTION_DAYS
        )
        if retention_days <= 0:
            return None
        return self.env.cr.now() - timedelta(days=retention_days)
