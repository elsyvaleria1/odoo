import logging
from datetime import datetime, timedelta

from odoo import fields, models
from odoo.exceptions import LockError

from odoo.addons.calendar_microsoft.models.mixin_microsoft_calendar_sync import (
    microsoft_calendar_connection,
)
from odoo.addons.calendar_microsoft.utils.calendar_microsoft import InvalidSyncToken

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    def _sync_microsoft_calendar(self) -> bool:
        self.check_singleton()
        account = self._calendar_sync_account("microsoft")
        # the cron and the calendar view would otherwise both spend the token
        try:
            account.lock_for_update(allow_referencing=True)
        except LockError:
            _logger.info("skipping calendar sync, locked account of %s", self.login)
            return False
        account.last_sync_date = datetime.now()
        if self._calendar_sync_status("microsoft") != "sync_active":
            return False

        # Set the first synchronization date as an ICP parameter before writing the variable
        # the account's sync token below, so we identify the first synchronization.
        self._set_ICP_first_synchronization_date(fields.Datetime.now())

        calendar_service = self.env["calendar.event"]._get_microsoft_service()
        full_sync = not account.sync_token
        with microsoft_calendar_connection(self) as connection:
            try:
                events, next_sync_token = calendar_service.get_events(
                    account.sync_token, connection=connection
                )
            except InvalidSyncToken:
                events, next_sync_token = calendar_service.get_events(
                    connection=connection
                )
                full_sync = True
        account.sync_token = next_sync_token

        # Microsoft -> Odoo
        synced_events, synced_recurrences = (
            self.env["calendar.event"]._sync_microsoft2odoo(events)
            if events
            else (self.env["calendar.event"], self.env["calendar.recurrence"])
        )

        # Odoo -> Microsoft
        recurrences = self.env["calendar.recurrence"]._get_microsoft_records_to_sync(
            full_sync=full_sync
        )
        recurrences -= synced_recurrences
        recurrences._sync_odoo2microsoft()
        synced_events |= recurrences.calendar_event_ids

        events = self.env["calendar.event"]._get_microsoft_records_to_sync(
            full_sync=full_sync
        )
        (events - synced_events)._sync_odoo2microsoft()
        account.last_sync_date = datetime.now()

        return bool(events | synced_events) or bool(recurrences | synced_recurrences)

    def _calendar_sync_run(self, code: str) -> bool:
        if code != "microsoft":
            return super()._calendar_sync_run(code)
        return self.with_context(
            dont_notify=True, microsoft_calendar_syncing=True
        )._sync_microsoft_calendar()

    def _calendar_sync_restart(self, code: str) -> None:
        super()._calendar_sync_restart(code)
        if code == "microsoft":
            # what changed before the restart is not sent: see
            # `_get_microsoft_records_to_sync`
            self._calendar_sync_account("microsoft").last_sync_date = datetime.now()
            self.env["calendar.recurrence"]._restart_microsoft_sync()
            self.env["calendar.event"]._restart_microsoft_sync()

    def calendar_sync_stop(self, code: str) -> None:
        super().calendar_sync_stop(code)
        if code == "microsoft":
            self._calendar_sync_account("microsoft").last_sync_date = False

    def _set_ICP_first_synchronization_date(self, now) -> None:
        """
        Set the first synchronization date as an ICP parameter when applicable (param not defined yet
        and calendar never synchronized before). This parameter is used for not synchronizing previously
        created Odoo events and thus avoid spamming invitations for those events.
        """
        ICP = self.env["ir.config_parameter"].sudo()
        first_synchronization_date = ICP.get_param(
            "calendar_microsoft.sync.first_synchronization_date"
        )

        if not first_synchronization_date:
            # Check if any calendar has synchronized before by checking the user's tokens.
            any_calendar_synchronized = (
                self.env["calendar.sync.account"]
                .sudo()
                .search_count(
                    [("provider", "=", "microsoft"), ("sync_token", "!=", False)],
                    limit=1,
                )
            )

            # Check if any user synchronized its calendar before by saving the date token.
            # Add one minute of time diff for avoiding write time delay conflicts with the next sync methods.
            if not any_calendar_synchronized:
                ICP.set_param(
                    "calendar_microsoft.sync.first_synchronization_date",
                    now - timedelta(minutes=1),
                )
