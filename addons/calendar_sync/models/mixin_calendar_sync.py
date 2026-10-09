from odoo import api, models


class MixinCalendarSync(models.AbstractModel):
    """What the engine hears of an event's or a recurrence's life: a change
    to send, a record to insert, a deletion to pass on."""

    _name = "mixin.calendar.sync"
    _description = "Synchronized with external calendars"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        Account = self.env["calendar.sync.account"]
        applying = self.env.context.get("calendar_sync_applying")
        codes = [code for code in Account._engine_providers() if code != applying]
        if codes and not self.env.context.get("no_calendar_sync"):
            records._calendar_sync_queue(codes)
        return records

    def write(self, vals):
        result = super().write(vals)
        Account = self.env["calendar.sync.account"]
        applying = self.env.context.get("calendar_sync_applying")
        marked = []
        for code in Account._engine_providers():
            if (
                code == applying
                or self.env.user._calendar_sync_stopped(code)
                or not vals.keys()
                & Account._adapter_of(code)._synced_fields(self._name)
            ):
                continue
            Link = self.env["calendar.sync.link"]
            Link._of(self._calendar_sync_alone(), code).write(
                {"pending": True, "error": False}
            )
            if series := self._calendar_sync_series(vals):
                Link._of(series, code).write({"pending": True, "error": False})
            marked.append(code)
        if marked and not self.env.context.get("no_calendar_sync"):
            self._calendar_sync_alone()._calendar_sync_queue(marked)
            if series := self._calendar_sync_series(vals):
                series._calendar_sync_queue(marked)
        return result

    def _calendar_sync_alone(self):
        """These records but the events following their series: a provider
        holds those as the series, which is sent for them."""
        if self._name != "calendar.event":
            return self
        return self.filtered(
            lambda event: not (event.recurrence_id and event.follow_recurrence)
        )

    def _calendar_sync_series(self, vals):
        """The series a write to all of its events changes."""
        if self._name == "calendar.event" and vals.get("recurrence_update") == "all":
            return self.recurrence_id
        return None

    def unlink(self):
        Account = self.env["calendar.sync.account"]
        providers = Account._engine_providers()
        if not providers:
            return super().unlink()
        applying = self.env.context.get("calendar_sync_applying")
        accounts = Account._as_engine()
        for code, provider in providers.items():
            links = self.env["calendar.sync.link"]._of(self, code)
            if code == applying:
                # deleted in the provider's calendars already
                links.unlink()
                continue
            if provider.capabilities.client_insert_id:
                # an insert in flight may have landed under its own id
                for link in links.filtered(lambda l: not l.remote_id and l.insert_id):
                    link.remote_id = link.insert_id
            # one whose id the provider chooses stays a tombstone too: the item
            # it may have inserted is found by its insert id, then deleted
            unsent = links.filtered(lambda link: not (link.remote_id or link.insert_id))
            # dated now: a read after this is what tells whether it landed
            links.filtered(lambda link: not link.remote_id and link.insert_id).write(
                {"pending": False}
            )
            unsent.unlink()
            accounts |= (links - unsent).account_id
        # the links left become tombstones: their items are deleted next
        result = super().unlink()
        accounts._queue_push(self.browse())
        return result

    def _calendar_sync_queue(self, codes) -> None:
        """Have the accounts these records go out through send them."""
        Account = self.env["calendar.sync.account"]
        for code in codes:
            active = Account._actives(code)
            running = (
                active.account(self.env.user) if active(self.env.user) else Account
            )
            by_writer = {}
            for record in self:
                if writer := Account._writer(record, code, running, active):
                    by_writer[writer] = by_writer.get(writer, self.browse()) | record
            for writer, records in by_writer.items():
                writer._as_engine()._queue_push(records)
