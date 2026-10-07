from odoo import api, fields, models
from odoo.tools import frozendict


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
