from odoo import api, models

from odoo.addons.calendar_sync.remote import (
    CalendarSyncError,
    ErrorKind,
    RemoteChanges,
    RemoteEvent,
)


class CalendarSyncAdapter(models.AbstractModel):
    _name = "calendar.sync.adapter"
    _description = "Calendar Synchronization Adapter"

    @api.model
    def _list_changes(self, account, token: str | None) -> RemoteChanges:
        raise NotImplementedError

    @api.model
    def _find(self, account, universal_id: str) -> RemoteEvent | None:
        raise NotImplementedError

    @api.model
    def _insert(self, account, record, values: dict, insert_id: str) -> RemoteEvent:
        raise NotImplementedError

    @api.model
    def _patch(
        self, account, remote_id: str, record, values: dict
    ) -> RemoteEvent | None:
        raise NotImplementedError

    @api.model
    def _delete(self, account, remote_id: str) -> None:
        raise NotImplementedError

    @api.model
    def _answer(self, account, remote_id: str, state: str) -> None:
        raise NotImplementedError

    @api.model
    def _after_insert(self, account, record, remote: RemoteEvent) -> None:
        pass

    @api.model
    def _classify(self, error: Exception) -> CalendarSyncError:
        return CalendarSyncError(ErrorKind.TRANSIENT, str(error))

    @api.model
    def _synced_fields(self, model_name: str) -> frozenset[str]:
        raise NotImplementedError

    @api.model
    def _check_record(self, record) -> str | None:
        return None

    @api.model
    def _remote_values(self, record, account) -> dict:
        raise NotImplementedError

    @api.model
    def _odoo_values(self, remote: RemoteEvent, model_name: str, record) -> dict:
        raise NotImplementedError

    @api.model
    def _apply_series(
        self, account, master: RemoteEvent | None, occurrences, recurrence
    ):
        raise NotImplementedError
