import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.libs import secret_key
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

from odoo.addons.auth_totp.controllers.home import TRUSTED_DEVICE_AGE_DAYS
from odoo.addons.auth_totp.models.auth_user_client import add_trust_foreign_key
from odoo.addons.base.models.res_users import check_identity

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class AuthTotpTrust(models.Model):
    _name = "auth.totp.trust"
    _description = "TOTP Trust"
    _auto = False
    _allow_sudo_commands = False
    _access_anchors = frozendict({"owner": "user_id"})

    name = fields.Char(
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
    create_date = fields.Datetime(readonly=True)
    expiration_date = fields.Datetime(
        readonly=True,
        required=True,
    )

    def init(self) -> None:
        self.env.cr.execute("""
            CREATE TABLE IF NOT EXISTS auth_totp_trust (
                id serial PRIMARY KEY, name varchar NOT NULL,
                user_id integer NOT NULL REFERENCES res_users(id) ON DELETE CASCADE,
                expiration_date timestamp NOT NULL,
                index varchar(8) NOT NULL, key varchar NOT NULL,
                create_date timestamp DEFAULT (now() at time zone 'UTC')
            )
        """)
        self.env.cr.execute(
            "CREATE INDEX IF NOT EXISTS auth_totp_trust_user_index ON auth_totp_trust(user_id, index)"
        )
        add_trust_foreign_key(self.env.cr)

    @api.model
    @_debug.perf.timed
    def _issue(self, name):
        if self.env.user._is_public():
            raise AccessError(
                self.env._("Only an authenticated user can register TOTP trust.")
            )
        expires = self.env.cr.now() + timedelta(seconds=self._get_trusted_device_age())
        key = secret_key.generate()
        self.env.cr.execute(
            SQL(
                "INSERT INTO auth_totp_trust(name, user_id, expiration_date, index, key) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                name,
                self.env.uid,
                expires,
                key[: secret_key.INDEX_SIZE],
                secret_key.hash_key(key),
            )
        )
        (trust_id,) = self.env.cr.fetchone()
        self.env.user.invalidate_recordset(["totp_trust_ids"])
        _debug.lifecycle(
            "trust_issued", uid=self.env.uid, trust_id=trust_id, expires=expires
        )
        self.env["auth.event"]._append(
            [
                {
                    "event": "credential_issued",
                    "subject_user_id": self.env.uid,
                    "model_name": self._name,
                    "credential_ref": trust_id,
                }
            ]
        )
        return self.browse(trust_id), key

    @api.model
    @_debug.perf.timed
    def _resolve_trust_id(self, *, key: str | None, uid: int) -> int | None:
        if not uid or not isinstance(key, str) or len(key) != 40:
            return None
        with self.env.registry.cursor(readonly=True, primary=True) as cr:
            cr.execute(
                SQL(
                    "SELECT t.id, t.key FROM auth_totp_trust t "
                    "JOIN res_users u ON u.id = t.user_id "
                    "WHERE t.user_id = %s AND t.index = %s AND u.active "
                    "AND t.expiration_date > now() at time zone 'UTC'",
                    uid,
                    key[: secret_key.INDEX_SIZE],
                )
            )
            candidates = cr.fetchall()
        for trust_id, encoded in candidates:
            if secret_key.is_key_valid(key, encoded):
                _debug.logic("trust_verified", uid=uid, trust_id=trust_id)
                return trust_id
        _debug.logic("trust_refused", uid=uid, reason="no_valid_match")
        return None

    @check_identity
    def remove(self):
        return self._remove()

    def _remove(self):
        if not self:
            return {"type": "ir.actions.act_window_close"}
        if not self.env.is_system() and self.mapped("user_id") != self.env.user:
            raise AccessError(self.env._("You can only revoke your own TOTP trust."))
        _debug.lifecycle("trust_revoked", uid=self.env.uid, count=len(self))
        self.env["auth.event"]._append(
            [
                {
                    "event": "credential_revoked",
                    "subject_user_id": trust.user_id.id,
                    "model_name": self._name,
                    "credential_ref": trust.id,
                }
                for trust in self
            ]
        )
        self.sudo().unlink()
        return {"type": "ir.actions.act_window_close"}

    @api.autovacuum
    def _gc_expired_trust(self) -> None:
        self.env.cr.execute(
            "DELETE FROM auth_totp_trust WHERE expiration_date IS NULL OR expiration_date <= now() at time zone 'UTC'"
        )
        _debug.lifecycle("expired_trust_removed", count=self.env.cr.rowcount)

    def _get_trusted_device_age(self):
        ICP = self.env["ir.config_parameter"].sudo()
        try:
            nbr_days = int(
                ICP.get_param("auth_totp.trusted_device_age", TRUSTED_DEVICE_AGE_DAYS)
            )
            if nbr_days <= 0:
                nbr_days = None
        except ValueError:
            nbr_days = None

        if nbr_days is None:
            _logger.warning(
                "Invalid value for 'auth_totp.trusted_device_age', using default value."
            )
            nbr_days = TRUSTED_DEVICE_AGE_DAYS

        return nbr_days * 86400  # seconds
