from odoo import api, fields, models
from odoo.tools import frozendict, str2bool


class CalendarSyncAccount(models.Model):
    """One user's synchronization with one provider: where it stands, beside
    the user's own connection to the provider, which holds the tokens."""

    _name = "calendar.sync.account"
    _description = "Calendar Synchronization Account"
    _order = "user_id, provider"

    _access_anchors = frozendict(
        {
            "owner": models.Anchor("user_id", shared=False),
            "company": models.Anchor("user_id.company_id", shared=False),
        }
    )

    user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        required=True,
        ondelete="cascade",
    )
    provider = fields.Selection(
        selection=[],
        required=True,
    )
    sync_token = fields.Char(
        string="Next Sync Token",
        copy=False,
        classification="secret.credential",
        groups="base.group_system",
        help="Where the provider's next change list starts; empty asks for a full one.",
    )
    stopped = fields.Boolean(
        string="Synchronization Stopped",
        copy=False,
        help="The user stopped this synchronization; nothing is sent or read.",
    )
    last_sync_date = fields.Datetime(
        string="Last Synchronization",
        copy=False,
    )

    _user_provider_unique = models.Constraint(
        "UNIQUE(user_id, provider)",
        "A user synchronizes with a provider once.",
    )

    @api.model
    def _calendar_sync_providers(self) -> dict:
        """{code: CalendarSyncProvider} of the installed adapters."""
        return {}

    @api.model
    def _provider(self, code: str):
        return self._calendar_sync_providers()[code]

    @api.model
    def _find(self, user, code: str):
        """`user`'s account with `code`, elevated, empty when none exists."""
        return self.sudo().search(
            [("user_id", "=", user.id), ("provider", "=", code)], limit=1
        )

    @api.model
    def _for(self, user, code: str):
        """`user`'s account with `code`, created on first use, elevated."""
        return self._find(user, code) or self.sudo().create(
            {"user_id": user.id, "provider": code}
        )

    @api.model
    def _is_paused(self, code: str) -> bool:
        return str2bool(
            self.env.registry.settings.get(
                self.env, self._provider(code).paused_param, False
            ),
            default=False,
        )

    @api.model
    def _set_paused(self, code: str, paused: bool) -> None:
        self.env["ir.config_parameter"].sudo().set_param(
            self._provider(code).paused_param, paused
        )

    @api.model
    def _has_client(self, code: str) -> bool:
        return self.env.ref(self._provider(code).service)._has_oauth_client()

    @api.model
    def _cron_sync(self) -> None:
        """Every account whose user authorized it and did not stop it, provider
        by provider, a commit per user."""
        Users = self.env["res.users"]
        for code in self._calendar_sync_providers():
            if self._is_paused(code):
                continue
            for user in Users._calendar_sync_candidates(code):
                Users._calendar_sync_run_for_cron(user, code)
