import hashlib
import re
import secrets
from datetime import timedelta

from odoo import api, fields, models

from ..tools.authority import operating

TOKEN_TTL_MINUTES = 10
INVITATION_TTL_DAYS = 7
GROUP_LINK_TTL_MINUTES = 30
TOKEN_SHAPE = re.compile(r"^[A-Za-z0-9_-]{32}$")


class TelegramLinkToken(models.Model):
    """A single-use proof that the bearer may bind a Telegram account.

    Minted for a user by that user's own Odoo session, or for a contact by an
    administrator's invitation that reaches the contact out of band. Only its
    hash is stored; the token travels once, as `/start <token>`, and is
    consumed by a single atomic update, so two chats racing with the same
    token bind at most one account.
    """

    _name = "telegram.link.token"
    _description = "Telegram Link Token"
    _order = "id desc"

    token_hash = fields.Char(
        index=True,
        copy=False,
        readonly=True,
        required=True,
    )
    bot_id = fields.Many2one(
        comodel_name="telegram.bot",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        ondelete="cascade",
        help="Set when the user's own session minted it: the binding then "
        "names that user.",
    )
    method = fields.Selection(
        selection=[("session", "Session"), ("invitation", "Invitation")],
        readonly=True,
        required=True,
    )
    purpose = fields.Selection(
        selection=[
            ("bind", "Connect an Account"),
            ("group", "Connect a Group"),
            ("broadcast", "Connect a Channel"),
        ],
        default="bind",
        readonly=True,
        required=True,
    )
    res_model = fields.Char(
        string="Linked Model",
        readonly=True,
        help="For a group link, the model of the record the group is linked to.",
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Linked Record",
        readonly=True,
    )
    date_to = fields.Datetime(
        readonly=True,
        required=True,
    )
    consumed_at = fields.Datetime(readonly=True)
    consumed_account_id = fields.Many2one(
        comodel_name="telegram.account",
        readonly=True,
        ondelete="set null",
    )

    _token_hash_uniq = models.Constraint(
        "UNIQUE (token_hash)", "A link token is issued once."
    )

    @staticmethod
    def _hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @api.model
    def _issue_for_session(self, bot):
        user = self.env.user
        return self._issue(
            bot,
            partner=user.partner_id,
            user=user,
            method="session",
            ttl=timedelta(minutes=TOKEN_TTL_MINUTES),
        )

    @api.model
    def _issue_invitation(self, bot, partner):
        return self._issue(
            bot,
            partner=partner,
            user=None,
            method="invitation",
            ttl=timedelta(days=INVITATION_TTL_DAYS),
        )

    @api.model
    def _issue_group_link(self, bot, record, purpose="group"):
        user = self.env.user
        return self._issue(
            bot,
            partner=user.partner_id,
            user=user,
            method="session",
            ttl=timedelta(minutes=GROUP_LINK_TTL_MINUTES),
            purpose=purpose,
            res_model=record._name,
            res_id=record.id,
        )

    @api.model
    def _issue(self, bot, *, partner, user, method, ttl, **vals):
        token = secrets.token_urlsafe(24)
        operating(self).create(
            {
                "token_hash": self._hash(token),
                "bot_id": bot.id,
                "partner_id": partner.id,
                "user_id": user.id if user else False,
                "method": method,
                "date_to": fields.Datetime.now() + ttl,
                **vals,
            }
        )
        return token

    @api.model
    def _consume(self, bot, token, account, purpose="bind"):
        if not token or not TOKEN_SHAPE.match(token):
            return self.browse()
        self.flush_model(["token_hash", "bot_id", "purpose", "consumed_at", "date_to"])
        self.env.cr.execute(
            """
            UPDATE telegram_link_token
               SET consumed_at = now() at time zone 'utc',
                   consumed_account_id = %s
             WHERE token_hash = %s
               AND bot_id = %s
               AND purpose = %s
               AND consumed_at IS NULL
               AND date_to > now() at time zone 'utc'
         RETURNING id
            """,
            (account.id or None, self._hash(token), bot.id, purpose),
        )
        row = self.env.cr.fetchone()
        if not row:
            return self.browse()
        link = operating(self).browse(row[0])
        link.invalidate_recordset(["consumed_at", "consumed_account_id"])
        return link

    @api.autovacuum
    def _gc_spent_tokens(self) -> None:
        threshold = fields.Datetime.now() - timedelta(days=1)
        self.search(
            ["|", ("consumed_at", "<", threshold), ("date_to", "<", threshold)]
        ).unlink()
