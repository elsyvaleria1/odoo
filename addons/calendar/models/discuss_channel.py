from odoo import api, fields, models
from odoo.fields import Domain


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    calendar_event_ids = fields.One2many(
        comodel_name="calendar.event",
        inverse_name="videocall_channel_id",
    )

    def _is_call_invitation_required(self) -> bool:
        if self.calendar_event_ids:
            return False
        return super()._is_call_invitation_required()

    @api.model
    def _get_meeting_backed_domain(self, event_domain=Domain.TRUE):
        return Domain("calendar_event_ids", "any!", event_domain)

    @api.model
    def _get_meeting_today_domain(self):
        planned_today = self._get_meeting_backed_domain(
            self.env["calendar.event"]._get_today_domain()
        )
        ad_hoc_today = super()._get_meeting_today_domain() & ~(
            self._get_meeting_backed_domain()
        )
        return planned_today | ad_hoc_today

    @api.model
    def _get_meeting_not_over_domain(self):
        still_to_come = self._get_meeting_backed_domain(
            Domain("stop", ">=", fields.Datetime.now())
        )
        return (
            super()._get_meeting_not_over_domain()
            | still_to_come
            | Domain("parent_channel_id", "any", still_to_come)
        )

    @api.depends(
        "calendar_event_ids.start",
        "calendar_event_ids.stop",
        "parent_channel_id.calendar_event_ids.start",
        "parent_channel_id.calendar_event_ids.stop",
    )
    def _compute_meeting_dt(self) -> None:
        super()._compute_meeting_dt()
        now = fields.Datetime.now()
        events_by_channel = (
            (self | self.parent_channel_id)
            .calendar_event_ids.sorted("start")
            .grouped("videocall_channel_id")
        )
        for channel in self:
            events = events_by_channel.get(channel.parent_channel_id or channel)
            if not events:
                continue
            event = next((event for event in events if event.stop >= now), events[-1])
            channel.meeting_start_dt = event.start
            channel.meeting_stop_dt = event.stop

    def _with_meeting_channel_privilege(self):
        return self.with_privilege(
            "calendar.privilege_keep_meeting_channels",
            "mail.privilege_configure_channels",
            reason="a meeting's editor keeps its video call channel in line",
        )

    def _retire_orphan_meeting_channels(self) -> None:
        channels = (
            self._with_meeting_channel_privilege()
            .with_context(active_test=False)
            .filtered(lambda channel: not channel.calendar_event_ids)
        )
        with_history = channels.filtered("message_count")
        with_history.channel_member_ids.unpin_dt = fields.Datetime.now()
        if orphans := channels - with_history:
            orphans.unlink()
