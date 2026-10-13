import datetime
import logging
from hashlib import sha256

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.libs import secret_key
from odoo.libs.debug_log import DebugLog
from odoo.libs.secret_key import INDEX_SIZE
from odoo.service import api_scope
from odoo.tools import SQL, frozendict

from .res_users import check_identity

_logger = logging.getLogger(__name__)

_debug = DebugLog(__name__)


class ResUsersApikeys(models.Model):
    _name = "res.users.apikeys"
    _description = "Users API Keys"
    _auto = False
    _allow_sudo_commands = False
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    name = fields.Char(
        string="Description",
        readonly=True,
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    scope_id = fields.Many2one(
        comodel_name="res.users.apikeys.scope",
        index=True,
        readonly=True,
        ondelete="cascade",
        help="The one door this key opens. Empty only on a key made before "
        "every key named its door: such a key opens the RPC doors alone.",
    )
    create_date = fields.Datetime(
        string="Creation Date",
        readonly=True,
    )
    expiration_date = fields.Datetime(readonly=True)

    def init(self) -> None:
        table = SQL.identifier(self._table)
        self.env.cr.execute(
            SQL(
                """
                CREATE TABLE IF NOT EXISTS %s (
                    id serial primary key,
                    name varchar not null,
                    user_id integer not null REFERENCES res_users(id) ON DELETE CASCADE,
                    scope_id integer REFERENCES res_users_apikeys_scope(id) ON DELETE CASCADE,
                    expiration_date timestamp without time zone,
                    index varchar(8) not null CHECK (char_length(index) = 8),
                    key varchar not null,
                    create_date timestamp without time zone DEFAULT (now() at time zone 'UTC')
                )
                """,
                table,
            )
        )

        index_name = self._table + "_user_id_index_idx"
        if len(index_name) > 63:
            index_name = (
                self._table[:50]
                + "_idx_"
                + sha256(self._table.encode()).hexdigest()[:8]
            )
        self.env.cr.execute(
            SQL(
                "CREATE INDEX IF NOT EXISTS %s ON %s (user_id, index)",
                SQL.identifier(index_name),
                table,
            )
        )

    @check_identity
    def remove(self) -> dict[str, str]:
        return self._remove()

    def _remove(self) -> dict[str, str]:
        if not self:
            _debug.logic("apikeys_remove_noop", uid=self.env.uid)
            return {"type": "ir.actions.act_window_close"}
        if self.env.is_system() or self.mapped("user_id") == self.env.user:
            keys = self.sudo()
            ip = request.httprequest.remote_addr if request else "n/a"
            _logger.info(
                "API key(s) removed: scope: <%s> for '%s' (#%s) from %s",
                keys.mapped("scope_id.key"),
                self.env.user.login,
                self.env.uid,
                ip,
            )
            _debug.lifecycle("apikeys_removed", count=len(self), by=self.env.uid)
            self.env["auth.event"]._append(
                [
                    {
                        "event": "credential_revoked",
                        "subject_user_id": key.user_id.id,
                        "model_name": self._name,
                        "credential_ref": key.id,
                    }
                    for key in keys
                ]
            )
            keys.unlink()
            return {"type": "ir.actions.act_window_close"}
        _debug.logic(
            "apikeys_remove_refused",
            uid=self.env.uid,
            owners=self.mapped("user_id").ids,
        )
        raise AccessError(
            self.env._(
                "You can not remove API keys unless they're yours or you are a system user"
            )
        )

    def unlink(self) -> bool:
        _debug.lifecycle("apikeys_unlinked", count=len(self))
        res = super().unlink()
        self.env.registry.clear_cache()
        return res

    def _match_key(
        self, scope: str, key: str
    ) -> tuple[int, datetime.datetime | None] | None:
        scope_id, active = self.env["res.users.apikeys.scope"]._get_declared_state(
            scope
        )
        if not active:
            _debug.logic("apikey_rejected", scope=scope, reason="scope_archived")
            return None
        door = SQL("k.scope_id = %s", scope_id)
        if scope == api_scope.RPC_SCOPE:
            door = SQL("(%s OR k.scope_id IS NULL)", door)
        self.env.cr.execute(
            SQL(
                """
                SELECT k.user_id, k.key, k.expiration_date
                FROM %s k
                INNER JOIN res_users u ON (u.id = k.user_id)
                WHERE u.active AND k.index = %s AND %s
                  AND (k.expiration_date IS NULL
                       OR k.expiration_date >= now() at time zone 'utc')
                """,
                SQL.identifier(self._table),
                key[:INDEX_SIZE],
                door,
            )
        )
        candidates = self.env.cr.fetchall()
        _debug.perf.count("apikey_candidates", scope=scope, candidates=len(candidates))
        for user_id, current_key, expiration_date in candidates:
            if secret_key.is_key_valid(key, current_key):
                _debug.logic(
                    "apikey_matched", scope=scope, uid=user_id, expires=expiration_date
                )
                return user_id, expiration_date
        _debug.logic("apikey_rejected", scope=scope, candidates=len(candidates))
        return None

    def _get_user_id_for_key(self, *, scope: str, key: str) -> int | None:
        if not scope or not key:
            _debug.logic("apikey_check_refused", reason="missing_scope_or_key")
            msg = "scope and key required"
            raise ValueError(msg)
        match = self._match_key(scope, key)
        return match[0] if match else None

    def _get_max_duration(self) -> float:
        return (
            max(
                (group.api_key_duration for group in self.env.user.all_group_ids),
                default=0.0,
            )
            or 1.0
        )

    def _check_expiration_date(self, date: datetime.datetime | None) -> None:
        if self.env.is_system():
            _debug.logic(
                "apikey_expiration_unchecked", uid=self.env.uid, reason="system"
            )
            return
        if not date:
            _debug.logic("apikey_expiration_rejected", uid=self.env.uid, reason="unset")
            raise ValidationError(
                self.env._("The API key must have an expiration date")
            )
        max_duration = self._get_max_duration()
        if date > fields.Datetime.now() + datetime.timedelta(days=max_duration):
            _debug.logic(
                "apikey_expiration_rejected",
                uid=self.env.uid,
                reason="too_far",
                max_days=max_duration,
            )
            raise ValidationError(
                self.env._(
                    "You cannot exceed %(duration)s days.", duration=max_duration
                )
            )

    def _check_generate_access(self) -> None:
        if not self.env.user._is_internal():
            _debug.logic("apikey_generate_refused", uid=self.env.uid)
            raise AccessError(self.env._("Only internal users can create API keys"))

    def _generate(
        self,
        scope: str,
        name: str,
        expiration_date: datetime.datetime | None,
    ) -> str:
        self._check_generate_access()
        self._check_expiration_date(expiration_date)
        scope_id, active = self.env["res.users.apikeys.scope"]._get_declared_state(
            scope
        )
        if not active:
            raise UserError(
                self.env._(
                    "The API key scope %(key)s is archived: a key bound to "
                    "it would open nothing.",
                    key=scope,
                )
            )
        k = secret_key.generate()
        self.env.cr.execute(
            SQL(
                """
                INSERT INTO %s (name, user_id, scope_id, expiration_date, key, index)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                SQL.identifier(self._table),
                name,
                self.env.user.id,
                scope_id,
                expiration_date or None,
                secret_key.hash_key(k),
                k[:INDEX_SIZE],
            )
        )

        (key_id,) = self.env.cr.fetchone()
        self.env.user.invalidate_recordset(["api_key_ids"])
        _debug.pipeline("apikey_inserted", uid=self.env.uid, scope=scope)
        self.env["auth.event"]._append(
            [
                {
                    "event": "credential_issued",
                    "subject_user_id": self.env.uid,
                    "model_name": self._name,
                    "credential_ref": key_id,
                }
            ]
        )

        ip = request.httprequest.remote_addr if request else "n/a"
        _logger.info(
            "%s generated: scope: <%s> for '%s' (#%s) from %s",
            self._description,
            scope,
            self.env.user.login,
            self.env.uid,
            ip,
        )
        _debug.lifecycle(
            "apikey_generated", uid=self.env.uid, scope=scope, expires=expiration_date
        )

        return k

    @api.autovacuum
    def _gc_user_apikeys(self) -> None:
        self.env.cr.execute(
            SQL(
                """
            DELETE FROM %s
            WHERE
                expiration_date IS NOT NULL AND
                expiration_date < now() at time zone 'utc'
        """,
                SQL.identifier(self._table),
            )
        )
        count = self.env.cr.rowcount
        if count:
            self.env.registry.clear_cache()
        _logger.info("GC %r delete %d entries", self._name, count)
        _debug.lifecycle("gc_apikeys", count=count)


class ResUsersApikeysShow(models.AbstractModel):
    _name = "res.users.apikeys.show"
    _description = "Show API Key"

    id = fields.Id()
    key = fields.Char(readonly=True)
