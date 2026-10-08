from odoo import api, fields, models
from odoo.fields import NEGATIVE_CONDITION_OPERATORS, Domain

from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent


class MixinMicrosoftCalendarSync(models.AbstractModel):
    _name = "mixin.microsoft.calendar.sync"
    _description = "Synchronize a record with Microsoft Calendar"

    microsoft_id = fields.Char(
        string="Organizer event Id",
        compute="_compute_microsoft_ids",
        inverse="_inverse_microsoft_ids",
        search="_search_microsoft_id",
        copy=False,
    )
    ms_universal_event_id = fields.Char(
        string="Universal event Id",
        compute="_compute_microsoft_ids",
        inverse="_inverse_microsoft_ids",
        search="_search_ms_universal_event_id",
        copy=False,
    )
    active = fields.Boolean(default=True)

    @api.model
    def _microsoft_id_fields(self) -> dict[str, str]:
        """{link field: field of this model} of the ids Outlook gave a record."""
        return {"remote_id": "microsoft_id", "universal_id": "ms_universal_event_id"}

    def _microsoft_links(self):
        """The Microsoft links of these records, elevated: one per calendar
        holding a record."""
        Link = self.env["calendar.sync.link"]._engine()
        fk = Link._field_of(self)
        return Link.search_fetch(
            [(fk, "in", self.ids), ("account_id.provider", "=", "microsoft")],
            [fk, "account_id", *self._microsoft_id_fields()],
        )

    def _microsoft_organizer(self):
        """The user organizing this record."""
        raise NotImplementedError

    @api.depends_context("uid")
    @api.depends(
        "calendar_sync_link_ids.remote_id",
        "calendar_sync_link_ids.universal_id",
        "calendar_sync_link_ids.remote_master_id",
    )
    def _compute_microsoft_ids(self) -> None:
        fk = self.env["calendar.sync.link"]._field_of(self)
        links = self._microsoft_links().grouped(fk)
        for record in self:
            # the ids of the current user's calendar, else of the organizer's
            rows = links.get(record, self.env["calendar.sync.link"])
            by_user = {row.account_id.user_id: row for row in rows}
            link = by_user.get(self.env.user) or by_user.get(
                record._microsoft_organizer(), rows[:1]
            )
            for link_field, field in self._microsoft_id_fields().items():
                record[field] = link[link_field] if link else False

    def _inverse_microsoft_ids(self) -> None:
        Link = self.env["calendar.sync.link"]._engine()
        links = self._microsoft_links().filtered(
            lambda link: link.account_id.user_id == self.env.user
        )
        own = links.grouped(Link._field_of(self))
        for record in self:
            record._microsoft_link(
                self.env.user,
                {
                    link_field: record[field] or False
                    for link_field, field in self._microsoft_id_fields().items()
                },
                own.get(record, Link),
            )

    def _microsoft_link(self, user, ids, link) -> None:
        """Keep the ids `user`'s calendar gave this record, as {link field:
        id}, in `link`, else in a new one; without an id Outlook knows the
        item by, it has none there."""
        self.check_singleton()
        Link = self.env["calendar.sync.link"]._engine()
        if not (ids.get("remote_id") or ids.get("universal_id")):
            link.unlink()
        elif link:
            link.write(
                {field: value for field, value in ids.items() if link[field] != value}
            )
        else:
            Link.create(
                {
                    **ids,
                    "account_id": self.env["calendar.sync.account"]
                    ._for(user, "microsoft")
                    .id,
                    Link._field_of(self): self.id,
                }
            )

    def _microsoft_applying(self) -> bool:
        """Whether this change comes from Outlook."""
        return bool(
            self.env.context.get("microsoft_calendar_syncing")
            or self.env.context.get("calendar_sync_applying") == "microsoft"
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

    def _search_microsoft_id(self, operator, value):
        return self._search_microsoft_link("remote_id", operator, value)

    def _search_ms_universal_event_id(self, operator, value):
        return self._search_microsoft_link("universal_id", operator, value)

    def _search_microsoft_link(self, link_field, operator, value):
        Link = self.env["calendar.sync.link"]._engine()
        fk = Link._field_of(self)
        microsoft = Domain("account_id.provider", "=", "microsoft")
        if operator == "=":
            operator, value = "in", [value]
        if operator in NEGATIVE_CONDITION_OPERATORS:
            return NotImplemented
        if operator != "in":
            return Domain(
                "id",
                "in",
                Link._search(microsoft & Domain(link_field, operator, value)).subselect(
                    fk
                ),
            )
        values = [v for v in value if v]
        domain = Domain.FALSE
        if values:
            domain |= Domain(
                "id",
                "in",
                Link._search(microsoft & Domain(link_field, "in", values)).subselect(
                    fk
                ),
            )
        if len(values) < len(value):
            domain |= Domain(
                "id",
                "not in",
                Link._search(
                    microsoft
                    & Domain(fk, "!=", False)
                    & Domain(link_field, "!=", False)
                ).subselect(fk),
            )
        return domain

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

    def _microsoft_values(self, fields_to_sync, initial_values=()):
        """This record as Outlook's API takes it, of `fields_to_sync`."""
        raise NotImplementedError

    def _microsoft_refusal(self) -> str | None:
        """Why Outlook would refuse this record; None when it would not."""
        raise NotImplementedError

    def _get_fields_microsoft_synced(self):
        """The fields of this model Outlook holds a copy of."""
        raise NotImplementedError

    def _is_video_call_required(self) -> bool:
        self.check_singleton()
        return True
