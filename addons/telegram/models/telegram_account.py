import logging

import psycopg

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict

from ..tools.authority import operating

_logger = logging.getLogger(__name__)

TIERS = ("contact", "portal", "internal")


class TelegramAccount(models.Model):
    """A Telegram person, the same across every bot of the database.

    Telegram gives a user one immutable id; the username and names are the
    owner's to change and only describe them. Who the person is in Odoo is
    decided by an active binding and nothing else.
    """

    _name = "telegram.account"
    _description = "Telegram Account"
    _order = "id desc"
    _access_anchors = frozendict({"partner": "partner_id"})

    tg_user_id = fields.Char(
        string="Telegram User ID",
        copy=False,
        readonly=True,
        required=True,
    )
    username = fields.Char(
        readonly=True,
        help="Display only: its owner can release it and somebody else can "
        "claim it, so it never decides who the account is.",
    )
    first_name = fields.Char(readonly=True)
    last_name = fields.Char(readonly=True)
    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    language_code = fields.Char(readonly=True)
    phone = fields.Char(
        copy=False,
        readonly=True,
        help="The number this Telegram account is registered with, as Telegram "
        "gave it when its owner shared their own contact with a bot. Telegram "
        "never says when it changes: the owner shares it again.",
    )
    phone_verified_at = fields.Datetime(
        string="Phone Verified On",
        copy=False,
        readonly=True,
    )
    binding_ids = fields.One2many(
        comodel_name="telegram.binding",
        inverse_name="account_id",
        string="Bindings",
        readonly=True,
    )
    binding_id = fields.Many2one(
        comodel_name="telegram.binding",
        string="Active Binding",
        compute="_compute_binding_id",
        store=True,
        index="btree_not_null",
        help="The active binding: who this person is in Odoo.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="binding_id.partner_id",
        store=True,
        index="btree_not_null",
    )
    chat_ids = fields.One2many(
        comodel_name="telegram.chat",
        inverse_name="account_id",
        readonly=True,
    )

    _tg_user_id_uniq = models.Constraint(
        "UNIQUE (tg_user_id)",
        "A Telegram user has one account.",
    )
    _tg_user_id_digits = models.Constraint(
        "CHECK (tg_user_id ~ '^[0-9]+$')",
        "A Telegram user id is digits.",
    )

    @api.depends("first_name", "last_name", "username", "tg_user_id")
    def _compute_name(self):
        for account in self:
            full = " ".join(filter(None, (account.first_name, account.last_name)))
            account.name = (
                full
                or (account.username and f"@{account.username}")
                or account.tg_user_id
            )

    @api.depends("binding_ids.state")
    def _compute_binding_id(self) -> None:
        for account in self:
            account.binding_id = account.binding_ids.filtered(
                lambda binding: binding.state == "active"
            )[:1]

    @api.model
    def _from_telegram(self, sender):
        """The account of an update's `from`, created on first sight and kept
        describing its owner; empty for a bot or a sender without an id."""
        if not sender or sender.get("is_bot") or not sender.get("id"):
            return self.browse()
        tg_user_id = str(sender["id"])
        vals = {
            "username": (sender.get("username") or "").lstrip("@").lower() or False,
            "first_name": sender.get("first_name") or False,
            "last_name": sender.get("last_name") or False,
            "language_code": sender.get("language_code") or False,
        }
        accounts = operating(self)
        account = accounts.search([("tg_user_id", "=", tg_user_id)], limit=1)
        if not account:
            try:
                with self.env.cr.savepoint():
                    return accounts.create({"tg_user_id": tg_user_id, **vals}).with_env(
                        self.env
                    )
            except psycopg.errors.UniqueViolation:
                # a concurrent update from the same person created it first
                account = accounts.search([("tg_user_id", "=", tg_user_id)], limit=1)
        changed = {key: value for key, value in vals.items() if account[key] != value}
        if changed:
            account.write(changed)
            if "language_code" in changed:
                # the bot speaks the language their app uses: so does its menu
                account.chat_ids._sync_command_menu()
        return account.with_env(self.env)

    def _acting_user(self, tier="internal"):
        """The Odoo user this Telegram person may act as, or no user.

        `internal` wants an internal user, `portal` accepts a share user too.
        The only answer comes from an active, unexpired binding whose user is
        active; a binding to a contact acts as the contact's only user of the
        tier, never as one picked among several.
        """
        self.check_singleton()
        users = self.env["res.users"]
        binding = operating(self).binding_id
        if not binding or (
            binding.expires_at and binding.expires_at <= fields.Datetime.now()
        ):
            return users
        if binding.user_id:
            candidates = binding.user_id
        else:
            candidates = binding.partner_id.with_context(active_test=True).user_ids
        candidates = candidates.filtered("active")
        if tier == "internal":
            candidates = candidates.filtered(lambda user: not user.share)
        if len(candidates) != 1:
            if len(candidates) > 1:
                _logger.warning(
                    "Telegram account %s binds contact %s, which has %s %s users: "
                    "acting as none",
                    self.id,
                    binding.partner_id.id,
                    len(candidates),
                    tier,
                )
            return users
        return candidates.with_env(self.env)

    def _contact(self):
        """The contact this person speaks as: the one they are bound to, else
        one made for them now and bound to them, until they prove who they
        are (the proven contact then absorbs it)."""
        self.check_singleton()
        partner = self._acting_partner()
        if partner:
            return partner
        account = operating(self)
        partner = account.env["res.partner"].create(
            {"name": account.name, "lang": account._lang()}
        )
        account._bind(partner, method="contact")
        return partner.with_env(self.env)

    def _update_phone(self, number) -> None:
        """Record the number Telegram vouched for: the one of a contact its
        owner shared whose user id is their own."""
        self.check_singleton()
        digits = "".join(character for character in number or "" if character.isdigit())
        if not digits:
            return
        operating(self).write(
            {"phone": f"+{digits}", "phone_verified_at": fields.Datetime.now()}
        )

    def _lang(self):
        """The active language closest to the one their Telegram app uses."""
        code = (self.language_code or "").replace("-", "_")
        if not code:
            return False
        # cached: the bot asks it of every message it answers
        active = [lang for lang, _name in self.env["res.lang"].get_installed()]
        exact = [lang for lang in active if lang.lower() == code.lower()]
        if exact:
            return exact[0]
        prefix = [lang for lang in active if lang.split("_")[0] == code[:2]]
        return prefix[0] if prefix else False

    def _acting_partner(self):
        """The contact this person speaks for, bound or not a user."""
        self.check_singleton()
        binding = operating(self).binding_id
        if binding.expires_at and binding.expires_at <= fields.Datetime.now():
            return self.env["res.partner"]
        return binding.partner_id.with_env(self.env)

    def _bind(self, partner, *, user=None, method, expires_at=False, invited_by=None):
        """Make `partner` (and `user`, when a session proved it) who this
        account is, superseding any binding it had."""
        self.check_singleton()
        bindings = operating(self.env["telegram.binding"])
        current = operating(self).binding_ids.filtered(lambda b: b.state == "active")
        current._revoke("superseded")
        # the index allows one active binding: the revoke must reach the table
        # before the new row does
        current.flush_recordset(["state"])
        binding = bindings.create(
            {
                "account_id": self.id,
                "partner_id": partner.id,
                "user_id": user.id if user else False,
                "method": method,
                "expires_at": expires_at,
                "invited_by_id": invited_by.id if invited_by else False,
            }
        )
        # the contact made for the person on first contact was a stand-in for
        # who they now proved to be: its history joins theirs (plan D6)
        stand_in = current.filtered(lambda b: b.method == "contact").partner_id
        if stand_in and stand_in != partner and not stand_in.user_ids:
            try:
                with self.env.cr.savepoint():
                    operating(self.env["wizard.res.partner.merge"])._merge(
                        (partner | stand_in).ids, partner, extra_checks=False
                    )
            except UserError as error:
                # the binding stands; a stand-in the merge refuses (one on a
                # hashed entry) keeps its own history
                _logger.warning(
                    "Telegram account %s: stand-in contact %s not merged into %s: %s",
                    self.id,
                    stand_in.id,
                    partner.id,
                    error,
                )
        return binding

    def action_revoke(self):
        self.check_access("write")
        self.binding_ids.filtered(lambda b: b.state == "active")._revoke("admin")
