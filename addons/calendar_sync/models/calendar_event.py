from odoo import api, fields, models


class CalendarEvent(models.Model):
    _name = "calendar.event"
    _inherit = ["calendar.event", "mixin.calendar.sync"]

    calendar_sync_link_ids = fields.One2many(
        comodel_name="calendar.sync.link",
        inverse_name="event_id",
        string="Calendar Synchronization Links",
        classification="calendar_sync.state",
        groups="base.group_system",
    )
    calendar_sync_linked = fields.Boolean(
        string="Held by an External Calendar",
        compute="_compute_calendar_sync_linked",
        help="An external calendar synchronized through the engine holds this event.",
    )

    @api.depends_context("uid")
    def _compute_calendar_sync_linked(self) -> None:
        codes = list(self.env["calendar.sync.account"]._engine_providers())
        linked = set()
        if codes and self.ids:
            linked = set(
                self.env["calendar.sync.link"]
                ._engine()
                .search_fetch(
                    [
                        ("event_id", "in", self.ids),
                        ("remote_id", "!=", False),
                        ("account_id.provider", "in", codes),
                    ],
                    ["event_id"],
                )
                .event_id.ids
            )
        for event in self:
            event.calendar_sync_linked = event.id in linked

    def _skip_send_mail_status_update(self):
        """A provider the event goes out through invites its attendees itself:
        through its organizer, or the current user when it has none."""
        sender = self.user_id or self.env.user
        if any(
            sender._calendar_sync_active(code)
            for code in self.env["calendar.sync.account"]._engine_providers()
        ):
            return True
        return super()._skip_send_mail_status_update()

    def _forget_sync_ids(self) -> None:
        super()._forget_sync_ids()
        Link = self.env["calendar.sync.link"]
        for code in self.env["calendar.sync.account"]._engine_providers():
            Link._of(self, code).unlink()
