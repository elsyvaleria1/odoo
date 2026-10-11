from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import frozendict

from odoo.addons.calendar_sync.remote import RemoteKind


class CalendarSyncLink(models.Model):
    """An event or a recurrence as one account's remote calendar knows it.

    A link to neither is a tombstone: the record is gone from Odoo and its
    remote copy is still to be deleted."""

    _name = "calendar.sync.link"
    _description = "Calendar Synchronization Link"

    _access_anchors = frozendict(
        {
            "owner": models.Anchor("account_id.user_id", shared=False),
            "company": models.Anchor("account_id.user_id.company_id", shared=False),
        }
    )

    account_id = fields.Many2one(
        comodel_name="calendar.sync.account",
        index=True,
        required=True,
        ondelete="cascade",
    )
    event_id = fields.Many2one(
        comodel_name="calendar.event",
        index="btree_not_null",
        ondelete="set null",
    )
    recurrence_id = fields.Many2one(
        comodel_name="calendar.recurrence",
        index="btree_not_null",
        ondelete="set null",
    )
    remote_id = fields.Char(
        string="Remote ID",
        copy=False,
        help="The item's id in this account's calendar; empty while its insert is in flight.",
    )
    universal_id = fields.Char(
        string="Universal ID",
        copy=False,
        help="The iCalendar UID, the same in every calendar holding the item.",
    )
    remote_master_id = fields.Char(
        string="Remote Series ID",
        copy=False,
        help="The id of the series the item belongs to, in this account's calendar.",
    )
    remote_etag = fields.Char(
        string="Remote Version",
        copy=False,
        help="The provider's version tag of the item when it was last read or sent.",
    )
    pending = fields.Boolean(
        copy=False,
        help="Odoo changed the record since the provider last heard of it.",
    )
    insert_id = fields.Char(
        string="Insert ID",
        copy=False,
        help="The id every attempt to insert the item sends, so a retry cannot insert it twice.",
    )
    error = fields.Char(
        copy=False,
        help="The provider's last refusal; the record is not sent again until it changes.",
    )
    answer_owed = fields.Char(
        copy=False,
        help="The answer to its invitation this attendee's calendar still owes the "
        "organizer: sent when the synchronization runs, kept until the provider "
        "takes it.",
    )

    _one_record = models.Constraint(
        "CHECK(num_nonnulls(event_id, recurrence_id) <= 1)",
        "A synchronization link is to an event or to a recurrence, not both.",
    )
    _account_event_unique = models.UniqueIndex(
        "(account_id, event_id) WHERE event_id IS NOT NULL",
        "An event is linked to an account's calendar once.",
    )
    _account_recurrence_unique = models.UniqueIndex(
        "(account_id, recurrence_id) WHERE recurrence_id IS NOT NULL",
        "A recurrence is linked to an account's calendar once.",
    )
    _account_event_remote_unique = models.UniqueIndex(
        "(account_id, remote_id) WHERE remote_id IS NOT NULL AND event_id IS NOT NULL",
        "An item of an account's calendar is linked to one event.",
    )
    _account_recurrence_remote_unique = models.UniqueIndex(
        "(account_id, remote_id) WHERE remote_id IS NOT NULL"
        " AND recurrence_id IS NOT NULL",
        "An item of an account's calendar is linked to one recurrence.",
    )
    _remote_id_idx = models.Index("(remote_id) WHERE remote_id IS NOT NULL")
    _universal_id_idx = models.Index("(universal_id) WHERE universal_id IS NOT NULL")

    @api.model
    def _engine(self):
        return self.with_privilege(
            "calendar_sync.privilege_engine",
            reason="the engine keeps the links of what it synchronizes",
        )

    def _record(self):
        self.check_singleton()
        return self.event_id or self.recurrence_id

    @api.model
    def _field_of(self, records) -> str:
        return "recurrence_id" if records._name == "calendar.recurrence" else "event_id"

    @api.model
    def _of(self, records, code: str):
        field = self._field_of(records)
        return self._engine().search(
            [(field, "in", records.ids), ("account_id.provider", "=", code)]
        )

    @api.model
    def _match(self, account, remotes) -> dict:
        Link = self._engine()
        code = account.provider
        found = {
            link.remote_id: link
            for link in Link.search(
                [
                    ("account_id", "=", account.id),
                    ("remote_id", "in", [remote.remote_id for remote in remotes]),
                ]
            )
        }
        linked = Domain.OR(
            [Domain("event_id", "!=", False), Domain("recurrence_id", "!=", False)]
        )

        def unmatched():
            return [remote for remote in remotes if remote.remote_id not in found]

        def adoptable():
            return [remote for remote in unmatched() if not remote.cancelled]

        client_ids = account._provider(code).capabilities.client_insert_id
        if inserting := {
            insert_id: remote
            for remote in unmatched()
            if (insert_id := remote.insert_id or (client_ids and remote.remote_id))
        }:
            for link in Link.search(
                [
                    ("account_id", "=", account.id),
                    ("remote_id", "=", False),
                    ("insert_id", "in", list(inserting)),
                ]
            ):
                remote = inserting[link.insert_id]
                if not link._record():
                    link.remote_id = remote.remote_id
                    found[remote.remote_id] = link
                    continue
                found[remote.remote_id] = Link._adopt(
                    account, link._record(), remote, link
                )

        by_universal_id = {r.universal_id: r for r in adoptable() if r.universal_id}
        if by_universal_id:
            for link in Link.search(
                Domain("account_id.provider", "=", code)
                & Domain("universal_id", "in", list(by_universal_id))
                & linked
            ):
                if remote := by_universal_id.pop(link.universal_id, None):
                    found[remote.remote_id] = Link._adopt(
                        account, link._record(), remote, link
                    )
        if account._provider(code).capabilities.shared_ids and (rest := unmatched()):
            by_id = {remote.remote_id: remote for remote in rest}
            for link in Link.search(
                Domain("account_id.provider", "=", code)
                & Domain("remote_id", "in", list(by_id))
                & linked
            ):
                if remote := by_id.pop(link.remote_id, None):
                    found[remote.remote_id] = Link._adopt(
                        account, link._record(), remote, link
                    )
        for remote in adoptable():
            if not remote.odoo_hint:
                continue
            model = (
                "calendar.recurrence"
                if remote.kind == RemoteKind.SERIES
                else "calendar.event"
            )
            record = self.env[model].browse(remote.odoo_hint).exists()
            if not record:
                continue
            links = Link._of(record, code)
            if not links or links.filtered(
                lambda link: link.account_id == account and not link.remote_id
            ):
                found[remote.remote_id] = Link._adopt(account, record, remote)
        return found

    @api.model
    def _adopt(self, account, record, remote, source=None):
        field = self._field_of(record)
        Link = self._engine()
        values = {
            "remote_id": remote.remote_id,
            "universal_id": remote.universal_id or (source and source.universal_id),
            "remote_master_id": remote.master_id,
        }
        if own := Link.search(
            [("account_id", "=", account.id), (field, "=", record.id)]
        ):
            own.write(values)
            return own
        return Link.create(
            {
                **values,
                "account_id": account.id,
                field: record.id,
                "pending": bool(source and source.pending),
            }
        )
