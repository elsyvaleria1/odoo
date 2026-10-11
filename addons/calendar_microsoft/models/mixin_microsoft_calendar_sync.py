from odoo import api, fields, models

from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent


class MixinMicrosoftCalendarSync(models.AbstractModel):
    _name = "mixin.microsoft.calendar.sync"
    _description = "Synchronize a record with Microsoft Calendar"

    active = fields.Boolean(default=True)

    def _microsoft_links(self):
        Link = self.env["calendar.sync.link"]._engine()
        fk = Link._field_of(self)
        return Link.search(
            [(fk, "in", self.ids), ("account_id.provider", "=", "microsoft")]
        )

    def _microsoft_applying(self) -> bool:
        return bool(
            self.env.context.get("microsoft_calendar_syncing")
            or self.env.context.get("calendar_sync_applying") == "microsoft"
        )

    def _calendar_applying(self) -> bool:
        return bool(
            self._microsoft_applying() or self.env.context.get("calendar_sync_applying")
        )

    def _microsoft_held(self):
        Link = self.env["calendar.sync.link"]
        return self.browse(Link._of(self, "microsoft")[Link._field_of(self)].ids)

    def _microsoft_tombstone(self) -> None:
        links = self._microsoft_links()
        accounts = links.account_id
        links.write({self.env["calendar.sync.link"]._field_of(self): False})
        accounts._as_engine()._queue_push(self.browse())

    def _microsoft_forget(self) -> None:
        self._microsoft_links().unlink()

    @api.model
    def _microsoft_to_odoo_values(self, microsoft_event: MicrosoftEvent, event=None):
        raise NotImplementedError

    @api.model
    def _get_microsoft_graph_timeout(self) -> int:
        timeout = self.env.registry.settings.get(
            self.env, "calendar_microsoft.graph_timeout", False
        )
        if not timeout or not timeout.isdecimal():
            return 5
        return max(1, int(timeout))

    def _microsoft_values(
        self, fields_to_sync, initial_values=(), series_master_id=None
    ):
        raise NotImplementedError

    def _microsoft_refusal(self) -> str | None:
        raise NotImplementedError

    def _get_fields_microsoft_synced(self):
        raise NotImplementedError
