from odoo import api, fields, models

from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent


class MixinMicrosoftCalendarSync(models.AbstractModel):
    _name = "mixin.microsoft.calendar.sync"
    _description = "Synchronize a record with Microsoft Calendar"

    active = fields.Boolean(default=True)

    def _microsoft_links(self):
        """The Microsoft links of these records, elevated: one per calendar
        holding a record."""
        Link = self.env["calendar.sync.link"]._engine()
        fk = Link._field_of(self)
        return Link.search(
            [(fk, "in", self.ids), ("account_id.provider", "=", "microsoft")]
        )

    def _microsoft_applying(self) -> bool:
        """Whether this change comes from Outlook."""
        return bool(
            self.env.context.get("microsoft_calendar_syncing")
            or self.env.context.get("calendar_sync_applying") == "microsoft"
        )

    def _calendar_applying(self) -> bool:
        """Whether this change comes from a synchronized calendar, Outlook's
        or another provider's, rather than from a person in Odoo."""
        return bool(
            self._microsoft_applying() or self.env.context.get("calendar_sync_applying")
        )

    def _microsoft_held(self):
        """These records but those no Outlook calendar holds."""
        Link = self.env["calendar.sync.link"]
        return self.browse(Link._of(self, "microsoft")[Link._field_of(self)].ids)

    def _microsoft_tombstone(self) -> None:
        """These records leave Outlook, though they stay in Odoo: each calendar
        holding one deletes it."""
        links = self._microsoft_links()
        accounts = links.account_id
        links.write({self.env["calendar.sync.link"]._field_of(self): False})
        accounts._as_engine()._queue_push(self.browse())

    def _microsoft_forget(self) -> None:
        """These records forget the ids Outlook gave them."""
        self._microsoft_links().unlink()

    @api.model
    def _microsoft_to_odoo_values(self, microsoft_event: MicrosoftEvent, event=None):
        """`microsoft_event` as values of this model; `event` is the record it
        updates, empty on creation."""
        raise NotImplementedError

    @api.model
    def _get_microsoft_graph_timeout(self) -> int:
        """How long an edit in the interface waits for Outlook, in seconds:
        five unless the system parameter says otherwise."""
        timeout = self.env.registry.settings.get(
            self.env, "calendar_microsoft.graph_timeout", False
        )
        if not timeout or not timeout.isdigit():
            return 5
        return max(1, int(timeout))

    def _microsoft_values(
        self, fields_to_sync, initial_values=(), series_master_id=None
    ):
        """This record as Outlook's API takes it, of `fields_to_sync`;
        `series_master_id` is its series' id in the calendar it is sent to."""
        raise NotImplementedError

    def _microsoft_refusal(self) -> str | None:
        """Why Outlook would refuse this record; None when it would not."""
        raise NotImplementedError

    def _get_fields_microsoft_synced(self):
        """The fields of this model Outlook holds a copy of."""
        raise NotImplementedError
