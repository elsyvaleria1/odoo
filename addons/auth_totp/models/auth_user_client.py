from odoo import api, fields, models
from odoo.db.schema import add_foreign_key, table_exists
from odoo.exceptions import AccessDenied
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

from odoo.addons.base.models.auth_user_client import _current_client_id

_debug = DebugLog(__name__)


def add_trust_foreign_key(cr) -> None:
    # Trust owns a hand-made table and expires rows in SQL; its links need a
    # database cascade even though the ORM skips foreign keys to _auto=False.
    if not (
        table_exists(cr, "auth_totp_trust")
        and table_exists(cr, "auth_user_client_totp_trust_rel")
    ):
        return
    cr.execute("""
        SELECT 1 FROM pg_constraint
        WHERE contype = 'f'
          AND conrelid = 'auth_user_client_totp_trust_rel'::regclass
          AND confrelid = 'auth_totp_trust'::regclass
    """)
    if not cr.rowcount:
        add_foreign_key(
            cr,
            "auth_user_client_totp_trust_rel",
            "trust_id",
            "auth_totp_trust",
            "id",
            "CASCADE",
        )
        _debug.lifecycle("trust_foreign_key_added")


class AuthUserClient(models.Model):
    _inherit = "auth.user.client"

    totp_trust_ids = fields.Many2many(
        comodel_name="auth.totp.trust",
        relation="auth_user_client_totp_trust_rel",
        column1="client_id",
        column2="trust_id",
        string="TOTP Trust Grants",
        copy=False,
        readonly=True,
    )

    has_valid_totp_trust = fields.Boolean(
        string="Trusted for 2FA",
        compute="_compute_has_valid_totp_trust",
    )

    @api.depends("totp_trust_ids.expiration_date")
    def _compute_has_valid_totp_trust(self) -> None:
        now = fields.Datetime.now()
        for client in self:
            client.has_valid_totp_trust = any(
                trust.expiration_date and trust.expiration_date > now
                for trust in client.totp_trust_ids
            )

    def init(self) -> None:
        super().init()
        add_trust_foreign_key(self.env.cr)

    def _check_login_authority(self, session) -> None:
        super()._check_login_authority(session)
        trust_id = session.pop("pre_totp_trust_id", None)
        if trust_id is not None:
            self._link_totp_trust(trust_id, session.uid)

    def _link_totp_trust(self, trust_id: int, uid: int) -> None:
        self.check_singleton()
        # The client lock comes before the trust lock, as in client revocation.
        self.env.cr.execute(
            SQL(
                "SELECT c.id FROM auth_user_client c "
                "JOIN auth_totp_trust t ON t.user_id = c.user_id "
                "WHERE c.id = %s AND c.user_id = %s AND c.active AND t.id = %s "
                "AND t.expiration_date > now() at time zone 'UTC' "
                "FOR UPDATE OF c FOR SHARE OF t",
                self.id,
                uid,
                trust_id,
            )
        )
        if not self.env.cr.fetchone():
            _debug.logic(
                "trust_binding_refused", uid=uid, reason="inactive_or_wrong_owner"
            )
            raise AccessDenied
        self.env.cr.execute(
            SQL(
                "INSERT INTO auth_user_client_totp_trust_rel(client_id, trust_id) "
                "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                self.id,
                trust_id,
            )
        )
        self.invalidate_recordset(["totp_trust_ids"])
        _debug.lifecycle("trust_linked", uid=uid, client_id=self.id, trust_id=trust_id)

    @api.model
    def _trust_current_client(self, trust_id: int) -> None:
        client_id = _current_client_id()
        if not client_id:
            raise AccessDenied
        self.browse(client_id)._link_totp_trust(trust_id, self.env.uid)

    def _revoke(self) -> bool:
        logout = super()._revoke()
        self.invalidate_recordset(["totp_trust_ids"])
        trusts = self.totp_trust_ids
        if trusts:
            trusts._remove()
            _debug.lifecycle("client_trust_removed", count=len(trusts))
        return logout

    @api.model
    def _gc_retention_filter(self, cutoff):
        return SQL(
            "%s AND NOT EXISTS (SELECT 1 FROM auth_user_client_totp_trust_rel rel "
            "JOIN auth_totp_trust t ON t.id = rel.trust_id "
            "WHERE rel.client_id = auth_user_client.id "
            "AND t.expiration_date > now() at time zone 'UTC')",
            super()._gc_retention_filter(cutoff),
        )
