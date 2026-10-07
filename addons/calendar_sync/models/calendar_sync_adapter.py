from odoo import api, models

from odoo.addons.calendar_sync.remote import (
    CalendarSyncError,
    ErrorKind,
    RemoteChanges,
    RemoteEvent,
)


class CalendarSyncAdapter(models.AbstractModel):
    """What the engine asks of a provider: its transport and the conversion
    of its items. A provider's adapter inherits this model under its own
    name and answers every method; the engine does the rest."""

    _name = "calendar.sync.adapter"
    _description = "Calendar Synchronization Adapter"

    # -- transport -----------------------------------------------------------

    @api.model
    def _list_changes(self, account, token: str | None) -> RemoteChanges:
        """The items changed in `account`'s calendar since `token`, or all of
        them in the synchronized window without one; raises TOKEN_INVALID
        when the provider no longer knows `token`."""
        raise NotImplementedError

    @api.model
    def _find(self, account, universal_id: str) -> RemoteEvent | None:
        """`account`'s copy of the item with this iCalendar UID."""
        raise NotImplementedError

    @api.model
    def _insert(self, account, record, values: dict, insert_id: str) -> RemoteEvent:
        """Insert `values` in `account`'s calendar, sending `insert_id`, the same
        on every attempt for one record."""
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
    def _after_insert(self, account, record, remote: RemoteEvent) -> None:
        """What `record` learns from its insert in `account`'s calendar."""

    @api.model
    def _classify(self, error: Exception) -> CalendarSyncError:
        """`error`, raised by the transport, as the engine handles it."""
        return CalendarSyncError(ErrorKind.TRANSIENT, str(error))

    # -- conversion ----------------------------------------------------------

    @api.model
    def _synced_fields(self, model_name: str) -> frozenset[str]:
        """The fields of `model_name` the provider holds a copy of."""
        raise NotImplementedError

    @api.model
    def _remote_values(self, record, account) -> dict:
        """`record` as the provider stores it."""
        raise NotImplementedError

    @api.model
    def _odoo_values(self, remote: RemoteEvent, model_name: str, record) -> dict:
        """`remote` as values of `model_name`; `record` is empty on creation."""
        raise NotImplementedError

    @api.model
    def _apply_series(self, account, master: RemoteEvent, occurrences, recurrence):
        """Create or update the recurrence of `master` and its events from
        `occurrences`; (recurrence, {remote id: event})."""
        raise NotImplementedError
