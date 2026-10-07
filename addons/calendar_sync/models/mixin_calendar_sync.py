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
            self.env["calendar.sync.link"]._of(self, code).write(
                {"pending": True, "error": False}
            )
            marked.append(code)
        if marked and not self.env.context.get("no_calendar_sync"):
            self._calendar_sync_queue(marked)
        return result

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
            unsent = links.filtered(lambda link: not link.remote_id)
            unsent.unlink()
            accounts |= (links - unsent).account_id
        # the links left become tombstones: their items are deleted next
        result = super().unlink()
        accounts._queue_push()
        return result

    def _calendar_sync_queue(self, codes) -> None:
        """Have the accounts these records go out through send them."""
        Account = self.env["calendar.sync.account"]
        accounts = Account._as_engine()
        for code in codes:
            running = (
                Account._for(self.env.user, code)
                if self.env.user._calendar_sync_active(code)
                else Account
            )
            for record in self:
                accounts |= Account._writer(record, code, running)
        accounts._queue_push()
