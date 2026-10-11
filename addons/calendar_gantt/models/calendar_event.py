from odoo import api, models
from odoo.libs.intervals import Intervals, invert_intervals
from odoo.tools import float_compare
from odoo.tools.date_utils import localized

from odoo.addons.base.models.resource_utils import capacity_timeline


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    @api.model
    def _gantt_unavailability(self, field_name, res_ids, start, stop, scale):
        # skip if not dealing with appointments
        if field_name not in ("resource_ids", "partner_ids"):
            return super()._gantt_unavailability(
                field_name, res_ids, start, stop, scale
            )

        # if viewing a specific appointment type generate unavailable intervals outside of the defined slots
        slots_unavailable_intervals = []
        appointment_type = self.env["appointment.type"]
        if appointment_type_id := self.env.context.get("default_appointment_type_id"):
            appointment_type = appointment_type.browse(appointment_type_id)

        if appointment_type:
            start_utc = localized(start)
            stop_utc = localized(stop)
            slot_available_intervals = [
                (slot["utc"][0], slot["utc"][1])
                for slot in appointment_type._slots_generate(
                    start_utc, stop_utc, "utc", reference_date=start
                )
            ]
            slots_unavailable_intervals = invert_intervals(
                slot_available_intervals, start_utc, stop_utc
            )

        # in staff view, add conflicting events to unavailabilities and return
        if field_name == "partner_ids":
            result = {}
            partner_unavailabilities = self._gantt_unavailabilities_events(
                start, stop, self.env["res.partner"].browse(res_ids)
            )
            for res_id in res_ids:
                unavailabilities = partner_unavailabilities.get(res_id, Intervals([]))
                unavailabilities |= Intervals(
                    [
                        (start, stop, self.env["res.partner"])
                        for start, stop in slots_unavailable_intervals
                    ]
                )
                result[res_id] = [
                    {"start": start, "stop": stop}
                    for start, stop, _ in unavailabilities
                ]
            return result

        resources = self.env["resource.resource"].browse(res_ids)
        # in multi-company, if people can't access some of the resources we don't really care
        if self.env.context.get("allowed_company_ids"):
            resources = resources.filtered_domain(
                [
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "in", self.env.context["allowed_company_ids"]),
                ]
            )

        availabilities_values = self.env[
            "appointment.type"
        ]._slot_availability_prepare_resources_values(resources, start, stop)
        resource_unavailabilities = availabilities_values["resource_unavailabilities"]
        booking_loads = availabilities_values["booking_loads"]

        result = {}
        for resource in resources:
            unavailabilities = Intervals(
                [(start, stop, set()) for start, stop in slots_unavailable_intervals]
            )
            unavailabilities |= Intervals(
                [
                    (start, stop, set())
                    for start, stop in resource_unavailabilities.get(resource, [])
                ]
            )
            # Resource projects free events, exclusive bookings, civil days and
            # other scheduling consumers into the same percentage timeline.
            # Summing booking lines across the display window loses simultaneity.
            unavailabilities |= Intervals(
                [
                    (localized(left), localized(right), set())
                    for left, right, load in capacity_timeline(
                        booking_loads[resource.id], start, stop
                    )
                    if float_compare(
                        load, resource.booking_limit_percentage, precision_digits=7
                    )
                    >= 0
                ]
            )
            result[resource.id] = [
                {"start": start, "stop": stop} for start, stop, _ in unavailabilities
            ]
        return result

    def _gantt_unavailabilities_events(self, start, stop, partners) -> dict:
        """Get a mapping from partner id to unavailabilities based on existing events.

        :returns: each partner id mapped to the ``Intervals`` of its busy slots, each
            carrying the ``res.partner`` record, e.g.
            {5: Intervals([(monday_morning, monday_noon, <res.partner>(5))])}
        :rtype: dict
        """
        # One lookup for the whole set. This sat *inside* the comprehension, so
        # the full search over `calendar_event` ran once per attendee -- a gantt
        # of twenty people asked the same question twenty times and threw away
        # nineteen of the answers, since each pass then read a single key out of
        # a mapping built for everybody.
        busy_by_partner = partners._get_busy_calendar_intervals(start, stop)
        return {
            attendee.id: Intervals(
                [
                    (localized(event_start), localized(event_stop), attendee)
                    for event_start, event_stop, _event in busy_by_partner.get(
                        attendee.id, []
                    )
                ]
            )
            for attendee in partners
        }

    @api.model
    def get_gantt_data(
        self,
        domain,
        groupby,
        read_specification,
        limit=None,
        offset=0,
        unavailability_fields=None,
        progress_bar_fields=None,
        start_date=None,
        stop_date=None,
        scale=None,
    ):
        """Filter out rows where the partner isn't linked to an staff user."""
        gantt_data = super().get_gantt_data(
            domain,
            groupby,
            read_specification,
            limit=limit,
            offset=offset,
            unavailability_fields=unavailability_fields,
            progress_bar_fields=progress_bar_fields,
            start_date=start_date,
            stop_date=stop_date,
            scale=scale,
        )
        if (
            self.env.context.get("appointment_booking_gantt_show_all_resources")
            and groupby
            and groupby[0] == "partner_ids"
        ):
            staff_partner_ids = (
                self.env["appointment.type"]
                .search([("schedule_based_on", "=", "users")])
                .staff_user_ids.partner_id.ids
            )
            gantt_data["groups"] = [
                group
                for group in gantt_data["groups"]
                if group.get("partner_ids")
                and group["partner_ids"][0] in staff_partner_ids
            ]
        return gantt_data
