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
    _remote_id_idx = models.Index("(remote_id) WHERE remote_id IS NOT NULL")
    _universal_id_idx = models.Index("(universal_id) WHERE universal_id IS NOT NULL")

    @api.model
    def _engine(self):
        """Links as the engine keeps them, whoever the synchronization runs as."""
        return self.with_privilege(
            "calendar_sync.privilege_engine",
            reason="the engine keeps the links of what it synchronizes",
        )

    def _record(self):
        """The event or the recurrence of this link; empty for a tombstone."""
        self.check_singleton()
        return self.event_id or self.recurrence_id

    @api.model
    def _of(self, records, code: str):
        """The links of `records` (events or recurrences) with provider `code`."""
        field = (
            "recurrence_id" if records._name == "calendar.recurrence" else "event_id"
        )
        return self._engine().search(
            [(field, "in", records.ids), ("account_id.provider", "=", code)]
        )

    @api.model
    def _match(self, account, remotes) -> dict:
        """{remote id: `account`'s link} of the `remotes` Odoo holds; a
        tombstone answers for an item whose deletion Odoo still owes. An item
        Odoo knows through another account's link, its iCalendar UID or the
        provider's hint is adopted: `account` gets a link of its own."""
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

        by_universal_id = {r.universal_id: r for r in unmatched() if r.universal_id}
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
        for remote in unmatched():
            if not remote.odoo_hint:
                continue
            model = (
                "calendar.recurrence"
                if remote.kind == RemoteKind.SERIES
                else "calendar.event"
            )
            record = self.env[model].browse(remote.odoo_hint).exists()
            # a record linked already is another item's: a split series
            # carries the properties of the one it was split from
            if record and not Link._of(record, code):
                found[remote.remote_id] = Link._adopt(account, record, remote)
        return found

    @api.model
    def _adopt(self, account, record, remote, source=None):
        """`account`'s link of `record` to `remote`, created or corrected."""
        field = "recurrence_id" if record._name == "calendar.recurrence" else "event_id"
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
