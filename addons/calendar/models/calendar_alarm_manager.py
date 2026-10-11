from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models
from odoo.libs.sql import SQL
from odoo.tools import plaintext2html


class CalendarAlarm_Manager(models.AbstractModel):
    _name = "calendar.alarm_manager"
    _description = "Event Alarm Manager"

    def _get_alarm_delta_sql(self, alarm_type):
        return SQL(
            """
            SELECT rel.calendar_event_id,
                   max(alarm.duration_minutes) AS max_delta,
                   min(alarm.duration_minutes) AS min_delta
              FROM calendar_alarm_calendar_event_rel AS rel
              LEFT JOIN calendar_alarm AS alarm ON alarm.id = rel.calendar_alarm_id
             WHERE alarm.alarm_type = %s
             GROUP BY rel.calendar_event_id
            """,
            alarm_type,
        )

    def _get_alarm_events_sql(self, partners):
        partner_join = SQL("")
        if partners:
            partner_join = SQL(
                """INNER JOIN calendar_event_res_partner_rel AS part_rel
                           ON part_rel.calendar_event_id = cal.id
                          AND part_rel.res_partner_id = ANY(%s)""",
                list(partners.ids),
            )
        return SQL(
            """
            SELECT cal.id,
                   cal.start - interval '1' minute * calcul_delta.max_delta AS first_alarm,
                   cal.stop - interval '1' minute * calcul_delta.min_delta AS last_alarm,
                   cal.start AS first_meeting,
                   cal.stop AS last_meeting,
                   calcul_delta.min_delta,
                   calcul_delta.max_delta
              FROM calendar_event AS cal
              INNER JOIN calcul_delta ON calcul_delta.calendar_event_id = cal.id
              %s
             WHERE cal.active = True
            """,
            partner_join,
        )

    def _get_alarm_horizon_sql(self, seconds, partners=None):
        if seconds is not None:
            return SQL("now() at time zone 'utc' + %s * interval '1' second", seconds)
        partner_join = SQL("")
        if partners:
            partner_join = SQL(
                """INNER JOIN calendar_event_res_partner_rel AS part_rel
                           ON part_rel.calendar_event_id = cal.id
                          AND part_rel.res_partner_id = ANY(%s)""",
                list(partners.ids),
            )
        return SQL(
            """COALESCE(
                (SELECT MIN(cal.start - interval '1' minute * calcul_delta.max_delta)
                   FROM calendar_event cal
                   RIGHT JOIN calcul_delta ON calcul_delta.calendar_event_id = cal.id
                   %s
                  WHERE cal.start - interval '1' minute * calcul_delta.max_delta > now() at time zone 'utc'
                ) + interval '3' minute,
                now() at time zone 'utc'
            )""",
            partner_join,
        )

    def _get_next_potential_limit_alarm(
        self, alarm_type, seconds=None, partners=None
    ) -> dict[int, dict]:
        for model_name in ("calendar.alarm", "calendar.event", "calendar.recurrence"):
            self.env[model_name].flush_model()

        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                """
                WITH calcul_delta AS (%s)
                SELECT *
                  FROM (%s) AS all_events
                 WHERE all_events.first_alarm < %s
                   AND all_events.last_alarm > (now() at time zone 'utc')
                """,
                self._get_alarm_delta_sql(alarm_type),
                self._get_alarm_events_sql(partners),
                self._get_alarm_horizon_sql(seconds, partners=partners),
            )
        )

        result = {
            event_id: {
                "event_id": event_id,
                "first_alarm": first_alarm,
                "last_alarm": last_alarm,
                "first_meeting": first_meeting,
                "last_meeting": last_meeting,
                "min_duration": min_duration,
                "max_duration": max_duration,
            }
            for (
                event_id,
                first_alarm,
                last_alarm,
                first_meeting,
                last_meeting,
                min_duration,
                max_duration,
            ) in self.env.cr.fetchall()
        }

        events = self.env["calendar.event"].browse(result)
        return {key: result[key] for key in events._filtered_access("read").ids}

    def do_check_alarm_for_one_date(
        self,
        one_date,
        event,
        in_the_next_X_seconds,
        alarm_type,
        after=False,
    ):
        result = []
        future = fields.Datetime.now() + timedelta(seconds=in_the_next_X_seconds)
        acknowledged_until = fields.Datetime.from_string(after) if after else None
        for alarm in event.alarm_ids:
            if alarm.alarm_type != alarm_type:
                continue
            notify_at = one_date - timedelta(minutes=alarm.duration_minutes)
            if future <= notify_at:
                continue
            if acknowledged_until is not None and notify_at <= acknowledged_until:
                continue
            result.append(
                {
                    "alarm_id": alarm.id,
                    "event_id": event.id,
                    "notify_at": notify_at,
                }
            )
        return result

    @api.model
    def _get_notify_alert_extra_conditions(self):
        return SQL("")

    def _get_events_by_alarm_to_notify(self, alarm_type):
        extra_conditions = self._get_notify_alert_extra_conditions()
        now = fields.Datetime.now()
        lastcall = self.env.context.get("lastcall") or (now - timedelta(weeks=1))
        self.env.cr.execute(
            SQL(
                """
            SELECT alarm.id, event.id
              FROM calendar_event AS event
              JOIN calendar_alarm_calendar_event_rel AS event_alarm_rel
                ON event.id = event_alarm_rel.calendar_event_id
              JOIN calendar_alarm AS alarm
                ON event_alarm_rel.calendar_alarm_id = alarm.id
             WHERE alarm.alarm_type = %s
               AND event.active
               -- `duration_minutes` is a stored column, and its sibling query
               -- `_get_next_potential_limit_alarm` already reads it. This used
               -- to build the same interval by concatenating `duration` and
               -- `interval` into text and casting it per row.
               AND event.start - interval '1' minute * alarm.duration_minutes >= %s
               AND event.start - interval '1' minute * alarm.duration_minutes < %s
               %s
        """,
                alarm_type,
                lastcall,
                now,
                extra_conditions,
            )
        )

        events_by_alarm = {}
        for alarm_id, event_id in self.env.cr.fetchall():
            events_by_alarm.setdefault(alarm_id, []).append(event_id)
        return events_by_alarm

    @api.model
    def _send_reminder(self):
        events_by_alarm = self._get_events_by_alarm_to_notify("email")
        if not events_by_alarm:
            return

        force_send_limit = int(
            self.env.registry.settings.get(self.env, "mail.mail_force_send_limit", 100)
        )

        event_ids = list(
            {
                event_id
                for event_ids in events_by_alarm.values()
                for event_id in event_ids
            }
        )
        events = self.env["calendar.event"].browse(event_ids)
        now = fields.Datetime.now()
        attendees = events.filtered(lambda e: e.stop > now).attendee_ids.filtered(
            lambda a: a.state != "declined"
        )
        attendees_by_event = {}
        for attendee in attendees:
            attendees_by_event.setdefault(attendee.event_id.id, []).append(attendee.id)
        alarms = self.env["calendar.alarm"].browse(events_by_alarm.keys())
        for alarm in alarms:
            alarm_attendee_ids = [
                attendee_id
                for event_id in events_by_alarm[alarm.id]
                for attendee_id in attendees_by_event.get(event_id, [])
            ]
            alarm_attendees = self.env["calendar.attendee"].browse(alarm_attendee_ids)
            alarm_attendees.with_context(
                calendar_template_ignore_recurrence=True
            )._notify_attendees(
                alarm.mail_template_id,
                force_send=len(attendees) <= force_send_limit,
                notify_author=True,
            )

        events._setup_event_recurrent_alarms(events_by_alarm)

    @api.model
    def get_next_notif(self):
        partner = self.env.user.partner_id
        if not partner:
            return []

        all_meetings = self._get_next_potential_limit_alarm(
            "notification", partners=partner
        )
        meetings = self.env["calendar.event"].browse(all_meetings)
        time_limit = 3600 * 24
        all_notif = []
        for meeting in meetings:
            alerts = self.do_check_alarm_for_one_date(
                meeting.start,
                meeting,
                time_limit,
                "notification",
                after=partner.calendar_last_notif_ack,
            )
            all_notif.extend(self.do_notif_reminder(alert) for alert in alerts)
        return all_notif

    def do_notif_reminder(self, alert) -> dict | None:
        alarm = self.env["calendar.alarm"].browse(alert["alarm_id"])
        meeting = self.env["calendar.event"].browse(alert["event_id"])

        if alarm.alarm_type == "notification":
            message = Markup("%s") % meeting.display_time
            if alarm.body:
                message += plaintext2html(alarm.body)

            delta = alert["notify_at"] - fields.Datetime.now()
            delta = delta.seconds + delta.days * 3600 * 24

            return {
                "alarm_id": alarm.id,
                "event_id": meeting.id,
                "title": meeting.name,
                "message": message,
                "timer": delta,
                "notify_at": fields.Datetime.to_string(alert["notify_at"]),
            }
        return None

    def _notify_next_alarm(self, partner_ids) -> None:
        users = self.env["res.users"].search(
            [
                ("partner_id", "in", tuple(partner_ids)),
                ("group_ids", "in", self.env.ref("base.group_user").ids),
            ]
        )
        for user in users:
            notif = (
                self.with_user(user)
                .with_context(allowed_company_ids=user.company_ids.ids)
                .get_next_notif()
            )
            user._bus_send("calendar.alarm", notif)
