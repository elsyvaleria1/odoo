from itertools import batched
from uuid import uuid4

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL, frozendict

from ..tools.authority import counting_presence, operating

_METHODS = [
    ("session", "Proven from an Odoo session"),
    ("invitation", "Proven with an invitation"),
    ("migration", "Carried over from a chat link"),
    ("contact", "Contact created on first contact"),
]
_REVOKE_REASONS = [
    ("user", "Disconnected by its owner"),
    ("admin", "Revoked by an administrator"),
    ("superseded", "Superseded by a newer binding"),
    ("expired", "Expired unconfirmed"),
    ("departed", "Its person left"),
]


class TelegramBinding(models.Model):
    """Who a Telegram account is in Odoo, as both sides proved it.

    An active binding is the only thing that lets an update act as someone.
    It is created by consuming a link token -- an Odoo session minted it, or an
    administrator's invitation reached the contact -- and Telegram delivering
    the sender's id; revoking it is terminal. Every transition is journaled in
    telegram.binding.event, and in auth.event when a user is bound.
    """

    _name = "telegram.binding"
    _description = "Telegram Binding"
    _order = "id desc"
    _access_anchors = frozendict({"partner": "partner_id"})

    account_id = fields.Many2one(
        comodel_name="telegram.account",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        index="btree_not_null",
        readonly=True,
        ondelete="cascade",
        help="The user whose session proved the binding. Empty for an "
        "invitation to a contact: the contact's own user then acts.",
    )
    method = fields.Selection(
        selection=_METHODS,
        readonly=True,
        required=True,
    )
    invited_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Invited By",
        readonly=True,
        ondelete="set null",
        help="Who issued the invitation the contact opened, for a binding proven "
        "with one: whoever handed a contact the link could open it themselves.",
    )
    state = fields.Selection(
        selection=[("active", "Active"), ("revoked", "Revoked")],
        default="active",
        index=True,
        readonly=True,
        required=True,
    )
    proven_at = fields.Datetime(
        default=fields.Datetime.now,
        readonly=True,
        required=True,
    )
    expires_at = fields.Datetime(
        readonly=True,
        help="A binding carried over from a chat link lapses unless its owner "
        "confirms it from an Odoo session.",
    )
    revoked_at = fields.Datetime(readonly=True)
    revoked_reason = fields.Selection(
        selection=_REVOKE_REASONS,
        readonly=True,
    )

    _one_active_per_account = models.UniqueIndex(
        "(account_id) WHERE state = 'active'",
        "A Telegram account is one person at a time.",
    )
    _user_is_partner = models.Constraint(
        "CHECK (user_id IS NULL OR partner_id IS NOT NULL)",
        "A bound user comes with its contact.",
    )

    @api.constrains("user_id", "partner_id")
    def _check_user_partner(self) -> None:
        for binding in self:
            if binding.user_id and binding.user_id.partner_id != binding.partner_id:
                raise UserError(
                    self.env._("A binding's user must be the user of its contact.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        bindings = super().create(vals_list)
        bindings._journal("proven")
        operating(bindings.account_id.chat_ids)._sync_command_menu()
        return bindings

    def write(self, vals):
        if vals.keys() - {"state", "revoked_at", "revoked_reason"}:
            raise AccessError(self.env._("A binding's identity cannot change."))
        if self.filtered(lambda b: b.state == "revoked"):
            raise AccessError(self.env._("A revoked binding stays revoked."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_never(self) -> None:
        raise AccessError(
            self.env._("A binding is revoked, never deleted: its history stays.")
        )

    def _revoke(self, reason):
        active = self.filtered(lambda b: b.state == "active")
        if not active:
            return
        active.write(
            {
                "state": "revoked",
                "revoked_at": fields.Datetime.now(),
                "revoked_reason": reason,
            }
        )
        active._journal("revoked", reason=reason)
        if reason != "superseded":
            operating(active.account_id.chat_ids)._sync_command_menu()

    @api.model
    def _revoke_for_departed(self, partners) -> None:
        departed = partners.filtered(lambda partner: not self._is_present(partner))
        if departed:
            operating(self).search(
                [("state", "=", "active"), ("partner_id", "in", departed.ids)]
            )._revoke("departed")

    @api.model
    def _is_present(self, partner) -> bool:
        return bool(
            counting_presence(self.env["res.users"]).search_count(
                [("partner_id", "=", partner.id), ("active", "=", True)]
            )
        )

    def _journal(self, event, *, reason=None) -> None:
        self.env["telegram.binding.event"]._append(
            [
                {
                    "event": event,
                    "binding_ref": binding.id,
                    "account_ref": binding.account_id.id,
                    "partner_ref": binding.partner_id.id,
                    "user_ref": binding.user_id.id or None,
                    "method": binding.method,
                    "reason": reason,
                }
                for binding in self
            ]
        )
        users = [
            {
                "event": "credential_issued"
                if event == "proven"
                else "credential_revoked",
                "subject_user_id": binding.user_id.id,
                "model_name": self._name,
                "credential_ref": binding.id,
            }
            for binding in self
            if binding.user_id
        ]
        if users:
            self.env["auth.event"]._append(users)

    @api.model
    def _cron_expire(self):
        expired = self.search(
            [("state", "=", "active"), ("expires_at", "<=", fields.Datetime.now())]
        )
        expired._revoke("expired")
        return len(expired)

    def action_revoke(self):
        self.check_access("write")
        self._revoke("admin")


class TelegramBindingEvent(models.Model):
    _name = "telegram.binding.event"
    _description = "Telegram Binding Event"
    _order = "id desc"
    _log_access = False
    _allow_sudo_commands = False

    event = fields.Selection(
        selection=[("proven", "Proven"), ("revoked", "Revoked")],
        readonly=True,
        required=True,
    )
    occurred_at = fields.Datetime(
        readonly=True,
        required=True,
    )
    actor_ref = fields.Integer(readonly=True)
    binding_ref = fields.Integer(
        index=True,
        readonly=True,
        required=True,
    )
    account_ref = fields.Integer(
        index=True,
        readonly=True,
        required=True,
    )
    partner_ref = fields.Integer(
        readonly=True,
        required=True,
    )
    user_ref = fields.Integer(readonly=True)
    method = fields.Selection(
        selection=_METHODS,
        readonly=True,
    )
    reason = fields.Selection(
        selection=_REVOKE_REASONS,
        readonly=True,
    )
    correlation_id = fields.Char(
        readonly=True,
        required=True,
    )

    @api.model
    def _append(self, values):
        if not values:
            return self.browse()
        correlation_id = str(uuid4())
        now = self.env.cr.now()
        ids = []
        for batch in batched(values, 1000, strict=False):
            self.env.cr.execute(
                SQL(
                    "INSERT INTO telegram_binding_event (event, occurred_at, actor_ref, "
                    "binding_ref, account_ref, partner_ref, user_ref, method, reason, "
                    "correlation_id) VALUES %s RETURNING id",
                    SQL(", ").join(
                        SQL(
                            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            vals["event"],
                            now,
                            self.env.uid,
                            vals["binding_ref"],
                            vals["account_ref"],
                            vals["partner_ref"],
                            vals.get("user_ref"),
                            vals.get("method"),
                            vals.get("reason"),
                            correlation_id,
                        )
                        for vals in batch
                    ),
                )
            )
            ids.extend(row[0] for row in self.env.cr.fetchall())
        return self.browse(ids)

    @api.model_create_multi
    def create(self, vals_list):
        if not vals_list:
            return self.browse()
        raise AccessError(self.env._("Binding events are written by the binding."))

    def write(self, vals):
        if not self:
            return True
        raise AccessError(self.env._("Binding events cannot be changed."))

    @api.ondelete(at_uninstall=False)
    def _unlink_never(self) -> None:
        raise AccessError(self.env._("Binding events cannot be deleted."))
