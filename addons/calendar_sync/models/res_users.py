import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    calendar_sync_account_ids = fields.One2many(
        comodel_name="calendar.sync.account",
        inverse_name="user_id",
        string="Calendar Synchronizations",
        classification="calendar_sync.state",
        groups="base.group_system",
    )

    def _calendar_sync_existing_account(self, code: str):
        self.check_singleton()
        return self.sudo().calendar_sync_account_ids.filtered(
            lambda account: account.provider == code
        )

    def _calendar_sync_account(self, code: str):
        return self._calendar_sync_existing_account(code) or self.env[
            "calendar.sync.account"
        ]._for(self, code)

    def _calendar_sync_stopped(self, code: str) -> bool:
        return self._calendar_sync_existing_account(code).stopped

    def _calendar_sync_connection(self, code: str):
        Connection = self.env["integration.connection"]
        if not self:
            return Connection.browse()
        self.check_singleton()
        provider = self.env["calendar.sync.account"]._provider(code)
        return Connection._find_personal(self.env.ref(provider.service), self).filtered(
            lambda connection: connection._is_oauth_authorized()
        )

    def _calendar_sync_status(self, code: str) -> str:
        self.check_singleton()
        if self.env["calendar.sync.account"]._is_paused(code):
            return "sync_paused"
        stopped = self._calendar_sync_stopped(code)
        if self._calendar_sync_connection(code) and not stopped:
            return "sync_active"
        return "sync_stopped" if stopped else "sync_active"

    def _calendar_sync_active(self, code: str) -> bool:
        self.check_singleton()
        return bool(
            self._calendar_sync_connection(code)
            and self._calendar_sync_status(code) == "sync_active"
        )

    @api.model
    def _calendar_sync_candidates(self, code: str):
        Account = self.env["calendar.sync.account"]
        connections = (
            self.env["integration.connection"]
            .sudo()
            .search(
                [
                    (
                        "service_id",
                        "=",
                        self.env.ref(Account._provider(code).service).id,
                    ),
                    ("user_id", "!=", False),
                    ("res_model", "=", False),
                    ("credential_id", "!=", False),
                    ("needs_reauthorization", "=", False),
                ]
            )
        )
        stopped = (
            Account.sudo()
            .search([("provider", "=", code), ("stopped", "=", True)])
            .user_id
        )
        return (connections.user_id - stopped).sudo()

    @api.model
    def _calendar_sync_run_for_cron(self, user, code: str) -> None:
        _logger.info("Calendar Synchro - Starting synchronization for %s", user)
        try:
            user._calendar_sync_as_owner()._calendar_sync_run(code)
            self.env["ir.cron"]._commit_progress(1)
        except Exception:
            _logger.exception("[%s] Calendar Synchro - Exception!", user)
            self.env.cr.rollback()

    def _calendar_sync_as_owner(self):
        self.check_singleton()
        return self.with_user(self).sudo()

    def _calendar_sync_run(self, code: str) -> bool:
        if code not in self.env["calendar.sync.account"]._engine_providers():
            raise NotImplementedError(code)
        return self._calendar_sync_account(code)._as_engine()._calendar_sync()

    def _calendar_sync_restart(self, code: str) -> None:
        if code not in self.env["calendar.sync.account"]._engine_providers():
            return
        account = self._calendar_sync_account(code)._as_engine()
        self.env["calendar.sync.link"]._engine().search(
            [("account_id", "=", account.id), ("remote_id", "!=", False)]
        ).pending = True
        account._queue_push()

    @api.model
    def calendar_sync_providers(self) -> list[dict]:
        return [
            {"code": code, "label": provider.label, "key": provider.key}
            for code, provider in self.env["calendar.sync.account"]
            ._calendar_sync_providers()
            .items()
        ]

    def _check_calendar_sync_owner(self) -> None:
        self.check_singleton()
        if self != self.env.user and not self.env.is_admin():
            raise AccessError(
                self.env._("You may only change your own calendar synchronization.")
            )

    def calendar_sync_stop(self, code: str) -> None:
        self._check_calendar_sync_owner()
        self._calendar_sync_account(code).stopped = True

    def calendar_sync_restart(self, code: str) -> None:
        self._check_calendar_sync_owner()
        self._calendar_sync_account(code).stopped = False
        self._calendar_sync_restart(code)

    @api.model
    def check_calendar_credentials(self):
        res = super().check_calendar_credentials()
        Account = self.env["calendar.sync.account"]
        for code, provider in Account._calendar_sync_providers().items():
            res[provider.key] = Account._has_client(code)
        return res

    def check_synchronization_status(self):
        res = super().check_synchronization_status()
        credentials = self.check_calendar_credentials()
        for code, provider in (
            self.env["calendar.sync.account"]._calendar_sync_providers().items()
        ):
            status = "missing_credentials"
            if credentials.get(provider.key):
                status = self._calendar_sync_status(code)
                if status == "sync_active" and not self._calendar_sync_connection(code):
                    status = "sync_stopped"
            res[provider.key] = status
        return res

    def _has_any_active_synchronization(self) -> bool:
        return super()._has_any_active_synchronization() or (
            "sync_active" in self.check_synchronization_status().values()
        )

    @api.model
    def _calendar_provider_client_id(self, provider: str) -> str:
        Account = self.env["calendar.sync.account"]
        if provider not in Account._calendar_sync_providers():
            return super()._calendar_provider_client_id(provider)
        return self.env.ref(Account._provider(provider).service)._oauth_client_id()

    @api.model
    def _set_calendar_provider_client(
        self, provider: str, client_id: str, client_secret: str | None
    ) -> None:
        Account = self.env["calendar.sync.account"]
        if provider not in Account._calendar_sync_providers():
            super()._set_calendar_provider_client(provider, client_id, client_secret)
            return
        self.env.ref(Account._provider(provider).service)._set_oauth_client(
            client_id, client_secret
        )
