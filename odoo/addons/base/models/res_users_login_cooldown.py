import dataclasses
import datetime
import re

from odoo import SUPERUSER_ID, api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, hmac, is_hmac_valid, register_signed_scope

from .res_users_auth import PasswordStore

_debug = DebugLog(__name__)

LOGIN_DEVICE_COOKIE = "login_device"
LOGIN_DEVICE_SCOPE = register_signed_scope(
    "login_device",
    purpose="let the browser that signed in to an account keep signing in "
    "while others' failures lock that account; the browser's own failures "
    "still lock it",
    lifetime="undated: retired by the account's next password change, by "
    "revoking that browser or logging out all of the account's devices, by the "
    "browser's own failures past its budget, or once the browser has been idle "
    "past base.device_retention_days",
)
LOGIN_DEVICE_MAX_AGE = 400 * 24 * 60 * 60
LOGIN_DEVICE_BUDGET = 5
_LOGIN_DEVICES_KEPT = 8
_LOGIN_DEVICE_RE = re.compile(r"(\d{1,10})\.(\d{1,10})\.([0-9a-f]{64})", re.ASCII)

_EPOCH = datetime.datetime.min.replace(tzinfo=datetime.UTC)

_FORGET_AFTER = datetime.timedelta(days=1)


class ResUsersLoginCooldown(models.Model):
    _name = "res.users.login.cooldown"
    _description = "Login Failure Cooldown"
    _log_access = False

    source = fields.Char(
        index="btree",
        required=True,
        help="A client's address, an account (`account:<user id>`), a login "
        "no account carries (`login:<sha256 of the login>`), or a browser's "
        "login marker (`device:<device id>.<marker generation>`).",
    )
    failures = fields.Integer(
        default=0,
        required=True,
    )
    last_failure = fields.Datetime(
        index="btree",
        required=True,
    )

    _source_uniq = models.Constraint(
        "unique (source)",
        "There can be only one cooldown row per source.",
    )


@dataclasses.dataclass(slots=True)
class AuthAttempt:
    keys_only: bool
    by_key: bool = False


class LoginCooldown:

    __slots__ = ("registry",)

    def __init__(self, registry) -> None:
        self.registry = registry

    def _rows(self, cr):
        env = api.Environment(cr, SUPERUSER_ID, {})
        return env["res.users.login.cooldown"]

    def claim(self, cr, source: str) -> bool:
        cr.execute(
            SQL(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))",
                f"login_cooldown:{source}",
            )
        )
        claimed = bool(cr.fetchone()[0])
        _debug.logic("cooldown_claim", source=source, claimed=claimed)
        return claimed

    def states(
        self, cr, sources: list[str]
    ) -> dict[str, tuple[int, datetime.datetime]]:
        cr.execute(
            SQL(
                "SELECT source, failures, last_failure FROM res_users_login_cooldown"
                " WHERE source = ANY(%s)",
                sources,
            )
        )
        found = {
            source: (failures, last_failure.replace(tzinfo=datetime.UTC))
            for source, failures, last_failure in cr.fetchall()
        }
        _debug.logic("cooldown_state", sources=sources, found=sorted(found))
        return {source: found.get(source, (0, _EPOCH)) for source in sources}

    def record_failure(
        self,
        sources: list[str],
        delay: datetime.timedelta,
        device: MarkedDevice | None = None,
    ) -> None:
        now = fields.Datetime.now()
        with self.registry.cursor() as cr:
            cr.use_read_committed()
            cr.execute(
                SQL(
                    """
                    INSERT INTO res_users_login_cooldown (source, failures, last_failure)
                    SELECT source, 1, %s FROM unnest(%s::varchar[]) AS source
                    ORDER BY source
                    ON CONFLICT (source) DO UPDATE
                    SET failures = res_users_login_cooldown.failures + 1,
                        last_failure = EXCLUDED.last_failure
                    RETURNING source, failures
                    """,
                    now,
                    sources,
                )
            )
            counts = dict(cr.fetchall())
            _debug.lifecycle("cooldown_failure_counted", counts=counts)
            if device is not None and counts.get(device.source, 0) >= device.budget:
                device.retire(cr)
            horizon = now - max(delay, _FORGET_AFTER)
            expired = self._rows(cr).search([("last_failure", "<", horizon)])
            _debug.lifecycle("cooldown_rows_expired", count=len(expired))
            expired.unlink()

    def clear(self, sources: list[str]) -> None:
        with self.registry.cursor() as cr:
            rows = self._rows(cr).search([("source", "in", sources)])
            _debug.lifecycle("cooldown_cleared", sources=sources, rows=len(rows))
            rows.unlink()


@dataclasses.dataclass(frozen=True, slots=True)
class MarkedDevice:
    id: int
    marker_generation: int
    budget: int

    @property
    def source(self) -> str:
        return f"device:{self.id}.{self.marker_generation}"

    def retire(self, cr) -> None:
        cr.execute(
            SQL(
                "UPDATE auth_user_client SET marker_generation = marker_generation + 1"
                " WHERE id = %s AND marker_generation = %s",
                self.id,
                self.marker_generation,
            )
        )
        _debug.lifecycle("login_device_retired", device=self.id, spent=cr.rowcount)


class LoginDevice:

    __slots__ = ("env",)

    def __init__(self, env) -> None:
        self.env = env

    def _signed(self, uid: int, device_id: int, generations: tuple[int, int]) -> tuple:
        stored = PasswordStore(self.env).stored_hash(self.env["res.users"], uid)
        return uid, device_id, *generations, stored

    def _generations(self, uid: int, device_id: int) -> tuple[int, int] | None:
        days = self.env["auth.user.client"]._retention_days()
        recent = SQL(
            " AND last_activity >= (now() AT TIME ZONE 'UTC') - make_interval(days => %s)",
            days,
        )
        self.env.cr.execute(
            SQL(
                "SELECT session_generation, marker_generation FROM auth_user_client"
                " WHERE id = %s AND user_id = %s%s",
                device_id,
                uid,
                recent if days > 0 else SQL(),
            )
        )
        return self.env.cr.fetchone()

    def device(self, uid: int, cookie: str, budget: int) -> MarkedDevice | None:
        for marker in cookie.split("_")[:_LOGIN_DEVICES_KEPT]:
            match = _LOGIN_DEVICE_RE.fullmatch(marker)
            if match is None or int(match[1]) != uid:
                continue
            device_id = int(match[2])
            generations = self._generations(uid, device_id)
            valid = generations is not None and is_hmac_valid(
                self.env,
                LOGIN_DEVICE_SCOPE,
                self._signed(uid, device_id, generations),
                match[3],
            )
            _debug.logic("login_device_checked", uid=uid, device=device_id, valid=valid)
            return MarkedDevice(device_id, generations[1], budget) if valid else None
        return None

    def retire_all(self, uid: int) -> None:
        self.env.cr.execute(
            SQL(
                "UPDATE auth_user_client SET marker_generation = marker_generation + 1"
                " WHERE user_id = %s",
                uid,
            )
        )
        _debug.lifecycle("login_devices_retired", uid=uid, devices=self.env.cr.rowcount)
        self.env["auth.user.client"].invalidate_model(["marker_generation"])

    def cookie(self, uid: int, device_id: int, cookie: str | None) -> str | None:
        generations = self._generations(uid, device_id)
        if generations is None:
            return None
        signature = hmac(
            self.env, LOGIN_DEVICE_SCOPE, self._signed(uid, device_id, generations)
        )
        kept = [
            other
            for other in (cookie or "").split("_")
            if (match := _LOGIN_DEVICE_RE.fullmatch(other)) and int(match[1]) != uid
        ]
        _debug.lifecycle("login_device_issued", uid=uid, device=device_id)
        return "_".join([f"{uid}.{device_id}.{signature}", *kept][:_LOGIN_DEVICES_KEPT])
