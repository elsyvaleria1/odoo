from datetime import date, datetime, timedelta
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import freeze_time

from .common import TestWebGantt
from odoo.addons.web_gantt.models.models import Base


@freeze_time(datetime(2021, 1, 1))
class TestWebGanttReschedule(TestWebGantt):
    def test_reschedule_cascading_forward(self):
        """This test purpose is to ensure that the forward rescheduling is properly working."""
        # 1- consume buffer
        res = self.gantt_reschedule_consume_buffer(
            self.pill_1,
            {
                self.date_start_field_name: "2021-06-01 00:00:00",
                self.date_stop_field_name: "2021-06-01 10:00:00",
            },
        )
        moved_pills = self.pill_1 | self.pill_2 | self.pill_3 | self.pill_4
        self.assert_old_pills_vals(
            res, "success", "Tasks rescheduled", moved_pills, self.initial_dates
        )
        self.assertEqual(
            self.pill_1[self.date_stop_field_name],
            self.pill_2[self.date_start_field_name],
            "Pill 1 should move forward up to start of Pill 2.",
        )
        self.assertEqual(
            self.pill_2[self.date_stop_field_name],
            self.pill_3[self.date_start_field_name],
            "Pill 2 should move forward up to start of Pill 3.",
        )
        self.assertEqual(
            self.pill_3[self.date_stop_field_name],
            self.pill_4[self.date_start_field_name],
            "Pill 3 should move forward up to start of Pill 4.",
        )
        moved_pills.action_rollback_scheduling(res["old_vals_per_pill_id"])
        self.assert_not_replanned(moved_pills, self.initial_dates)

        # 2- maintain buffer
        res = self.gantt_reschedule_maintain_buffer(
            self.pill_1,
            {
                self.date_start_field_name: "2021-06-01 00:00:00",
                self.date_stop_field_name: "2021-06-01 10:00:00",
            },
        )
        self.assert_old_pills_vals(
            res, "success", "Tasks rescheduled", moved_pills, self.initial_dates
        )
        self.assertEqual(
            self.pill_1[self.date_stop_field_name] + timedelta(seconds=self.buffer12),
            self.pill_2[self.date_start_field_name],
            "Pill 2 should start after buffer12 after the end of Pill 1.",
        )
        self.assertEqual(
            self.pill_2[self.date_stop_field_name] + timedelta(seconds=self.buffer23),
            self.pill_3[self.date_start_field_name],
            "Pill 3 should start after buffer12 after the end of Pill 2.",
        )
        self.assertEqual(
            self.pill_3[self.date_stop_field_name] + timedelta(seconds=self.buffer34),
            self.pill_4[self.date_start_field_name],
            "Pill 4 should start after buffer12 after the end of Pill 3.",
        )

    def test_reschedule_cascading_backward(self):
        """This test purpose is to ensure that the backward rescheduling is properly working."""
        # 1- consume buffer
        res = self.gantt_reschedule_consume_buffer(
            self.pill_4,
            {
                self.date_start_field_name: "2021-03-01 00:00:00",
                self.date_stop_field_name: "2021-03-01 10:00:00",
            },
        )
        moved_pills = self.pill_1 | self.pill_2 | self.pill_3 | self.pill_4
        self.assert_old_pills_vals(
            res, "success", "Tasks rescheduled", moved_pills, self.initial_dates
        )
        self.assertEqual(
            self.pill_1[self.date_stop_field_name],
            self.pill_2[self.date_start_field_name],
            "Pill 1 should move backward up to start of Pill 2.",
        )
        self.assertEqual(
            self.pill_2[self.date_stop_field_name],
            self.pill_3[self.date_start_field_name],
            "Pill 2 should move backward up to start of Pill 3.",
        )
        self.assertEqual(
            self.pill_3[self.date_stop_field_name],
            self.pill_4[self.date_start_field_name],
            "Pill 3 should move backward up to start of Pill 4.",
        )
        moved_pills.action_rollback_scheduling(res["old_vals_per_pill_id"])
        self.assert_not_replanned(moved_pills, self.initial_dates)

        # 2- maintain buffer
        res = self.gantt_reschedule_maintain_buffer(
            self.pill_4,
            {
                self.date_start_field_name: "2021-03-01 00:00:00",
                self.date_stop_field_name: "2021-03-01 10:00:00",
            },
        )
        self.assert_old_pills_vals(
            res, "success", "Tasks rescheduled", moved_pills, self.initial_dates
        )
        self.assertEqual(
            self.pill_1[self.date_stop_field_name] + timedelta(seconds=self.buffer12),
            self.pill_2[self.date_start_field_name],
            "Pill 2 should start after buffer12 after the end of Pill 1.",
        )
        self.assertEqual(
            self.pill_2[self.date_stop_field_name] + timedelta(seconds=self.buffer23),
            self.pill_3[self.date_start_field_name],
            "Pill 3 should start after buffer12 after the end of Pill 2.",
        )
        self.assertEqual(
            self.pill_3[self.date_stop_field_name] + timedelta(seconds=self.buffer34),
            self.pill_4[self.date_start_field_name],
            "Pill 4 should start after buffer12 after the end of Pill 3.",
        )

    def test_not_in_past(self):
        """This test purpose is to ensure that:
        * Records are not rescheduled in the past.
        * A notification is returned when trying to reschedule a record in the past.
        """
        res = self.gantt_reschedule_consume_buffer(
            self.pill_4,
            {
                self.date_start_field_name: "2021-01-01 00:00:00",
                self.date_stop_field_name: "2021-01-01 10:00:00",
            },
        )
        self.assert_old_pills_vals(
            res,
            "warning",
            "Pill 3 cannot be scheduled in the past",
            self.env["test.web.gantt.pill"],
            self.initial_dates,
        )

    def test_conflicting_cascade_forward(self):
        """
        ┌────────────────────────┐                                       ┌──────────────────────────────────┐
        │pill_2_slave_in_conflict|<---------- -------------------------->|  pill_2_slave_not_in_conflict    |
        └────────────────────────┘          | |                          └──────────────────────────────────┘
        ┌────────────────────────┐      ┌─────────┐     ┌─────────┐      ┌──────────────────────────────────┐
        │ Pill 1                 │ ---> │ Pill 2  │-->  │ Pill 3  │ -->  │ Pill 4                           │
        └────────────────────────┘      └─────────┘     └─────────┘      └──────────────────────────────────┘
        ┌────────────────────────┐                           | |         ┌──────────────────────────────────┐
        │pill_3_slave_in_conflict│<--------------------------- --------->│ pill_3_slave_not_in_conflict     │
        └────────────────────────┘                                       └──────────────────────────────────┘

        When moving forward without conflicts, we only move records in conflict.
        When advancing pill 3 without creating conflicts with pill_3_slave_not_in_conflict and pill 4, they both should not move.
        we only move pill_3_slave_in_conflict to fix the conflict
        ancestors should not be impacted
        """
        self.pill_2_slave_in_conflict = self.create_pill(
            "Pill in conflict with Pill 2",
            self.pill_1_start_date,
            self.pill_1_stop_date,
            [self.pill_2.id],
        )
        self.pill_2_slave_not_in_conflict = self.create_pill(
            "Pill not in conflict with Pill 2",
            self.pill_4_start_date,
            self.pill_4_stop_date,
            [self.pill_2.id],
        )
        self.pill_3_slave_in_conflict = self.create_pill(
            "Pill in conflict with Pill 3",
            self.pill_1_start_date,
            self.pill_1_stop_date,
            [self.pill_3.id],
        )
        self.pill_3_slave_not_in_conflict = self.create_pill(
            "Pill not in conflict with Pill 3",
            self.pill_4_start_date,
            self.pill_4_stop_date,
            [self.pill_3.id],
        )
        moved_pills = self.pill_3 | self.pill_3_slave_in_conflict
        initial_dates_deep_copy = dict(self.initial_dates)
        initial_dates_deep_copy[self.pill_3_slave_in_conflict.name] = (
            self.pill_3_slave_in_conflict.date_start,
            self.pill_3_slave_in_conflict.date_stop,
        )

        res = self.gantt_reschedule_consume_buffer(
            self.pill_3,
            {
                self.date_start_field_name: "2021-03-04 00:00:00",
                self.date_stop_field_name: "2021-03-04 08:00:00",
            },
        )

        self.assert_old_pills_vals(
            res, "success", "Tasks rescheduled", moved_pills, initial_dates_deep_copy
        )
        self.assertEqual(
            self.pill_3[self.date_stop_field_name],
            self.pill_4[self.date_start_field_name],
            "pill_3 should have been rescheduled to the start of pill_4",
        )
        self.assertEqual(
            self.pill_3_slave_in_conflict[self.date_start_field_name],
            self.pill_3[self.date_stop_field_name],
            "pill_3_slave_in_conflict should have been rescheduled once pill_3 had been rescheduled.",
        )
        self.assertEqual(
            self.pill_3_slave_not_in_conflict[self.date_start_field_name],
            self.pill_3[self.date_stop_field_name],
            "pill_3_slave_not_in_conflict should not be rescheduled once as it is not in conflict with pill_3.",
        )
        self.assertEqual(
            (
                self.pill_2[self.date_start_field_name],
                self.pill_2[self.date_stop_field_name],
            ),
            (self.pill_2_start_date, self.pill_2_stop_date),
            "pill_2 should not be rescheduled.",
        )
        moved_pills.action_rollback_scheduling(res["old_vals_per_pill_id"])
        self.assert_not_replanned(moved_pills, initial_dates_deep_copy)

    def test_conflicting_cascade_backward(self):
        """
        ┌──────────────────────────────┐                                       ┌──────────────────────────────────┐
        |pill_2_master_not_in_conflict |----------- ---------------------------|  pill_2_master_in_conflict       |
        └──────────────────────────────┘          | |                          └──────────────────────────────────┘
                                                  v v
        ┌──────────────────────────────┐      ┌─────────┐     ┌─────────┐      ┌──────────────────────────────────┐
        │       Pill 1                 │ ---> │ Pill 2  │-->  │ Pill 3  │ -->  │ Pill 4                           │
        └──────────────────────────────┘      └─────────┘     └─────────┘      └──────────────────────────────────┘
                                                                   ^ ^
        ┌──────────────────────────────┐                           | |         ┌──────────────────────────────────┐
        | pill_3_master_not_in_conflict|---------------------------- ----------| pill_3_master_in_conflict        │
        └──────────────────────────────┘                                       └──────────────────────────────────┘

            When moving backward without conflicts, we only move records in conflict.
            When moving pill 2 to the end of pill 1 and pill_2_master_not_in_conflict without creating conflicts, they both should not move.
            we only move pill_2_master_in_conflict to fix the conflict
            children should not be impacted
        """
        self.pill_3_master_in_conflict = self.create_pill(
            "Pill in conflict with Pill 3",
            self.pill_4_start_date,
            self.pill_4_stop_date,
        )
        self.pill_3_master_not_in_conflict = self.create_pill(
            "Pill not in conflict with Pill 3",
            self.pill_1_start_date,
            self.pill_1_stop_date,
        )
        self.pill_3[self.dependency_field_name] = [
            Command.link(self.pill_3_master_in_conflict.id),
            Command.link(self.pill_3_master_not_in_conflict.id),
        ]
        self.pill_2_master_in_conflict = self.create_pill(
            "Pill in conflict with Pill 2",
            self.pill_4_start_date,
            self.pill_4_stop_date,
        )
        self.pill_2_master_not_in_conflict = self.create_pill(
            "Pill not in conflict with Pill 2",
            self.pill_1_start_date,
            self.pill_1_stop_date,
        )
        self.pill_2[self.dependency_field_name] = [
            Command.link(self.pill_2_master_in_conflict.id),
            Command.link(self.pill_2_master_not_in_conflict.id),
        ]
        moved_pills = self.pill_2 | self.pill_2_master_in_conflict
        initial_dates_deep_copy = dict(self.initial_dates)
        initial_dates_deep_copy[self.pill_2_master_in_conflict.name] = (
            self.pill_2_master_in_conflict.date_start,
            self.pill_2_master_in_conflict.date_stop,
        )
        res = self.gantt_reschedule_consume_buffer(
            self.pill_2,
            {
                self.date_start_field_name: "2021-03-01 16:00:00",
                self.date_stop_field_name: "2021-03-02 00:00:00",
            },
        )
        self.assert_old_pills_vals(
            res, "success", "Tasks rescheduled", moved_pills, initial_dates_deep_copy
        )
        self.assertEqual(
            self.pill_1[self.date_stop_field_name],
            self.pill_2[self.date_start_field_name],
        )
        self.assertEqual(
            self.pill_2_master_in_conflict[self.date_stop_field_name],
            self.pill_2[self.date_start_field_name],
            "pill_2_master_in_conflict should have been rescheduled once pill_2 had been rescheduled.",
        )
        moved_pills.action_rollback_scheduling(res["old_vals_per_pill_id"])
        self.assert_not_replanned(moved_pills, initial_dates_deep_copy)

    def test_pills2_reschedule_cascading_forward(self):
        """
        This test concerns pills2, when pill 0 is move ahead of task 8.
        As pills 1, 2, 3 are children of 0, they should be done after it,
        they should also be moved forward
        All the other pills should not move.
        """
        self.gantt_reschedule_consume_buffer(
            self.pills2_0,
            {
                self.date_start_field_name: "2024-03-16 14:00:00",
                self.date_stop_field_name: "2024-03-16 18:00:00",
            },
        )
        self.assert_not_replanned(
            self.pills2_4
            | self.pills2_5
            | self.pills2_6
            | self.pills2_7
            | self.pills2_8
            | self.pills2_9
            | self.pills2_10
            | self.pills2_11
            | self.pills2_12
            | self.pills2_13
            | self.pills2_14,
            self.initial_dates,
        )

        self.assertEqual(
            self.pills2_0[self.date_start_field_name],
            self.pills2_8[self.date_stop_field_name],
        )
        self.assertEqual(
            self.pills2_1[self.date_start_field_name],
            self.pills2_0[self.date_stop_field_name],
        )
        self.assertEqual(
            self.pills2_2[self.date_start_field_name],
            self.pills2_1[self.date_stop_field_name],
        )
        self.assertEqual(
            self.pills2_2[self.date_start_field_name],
            self.pills2_1[self.date_stop_field_name],
        )

    def test_pills2_reschedule_cascading_backward(self):
        """
        This test concerns pills2, when the left arrow is clicked. pill 8 should be moved behind pill 0
        As pills 4, 6, 5, 7 are ancestors for 8 and should be done before it, they should be moved backward.
        9 and 10 should not be impacted as they are not ancestors of 8.
        All the other pills should not move.
        """
        self.gantt_reschedule_consume_buffer(
            self.pills2_8,
            {
                self.date_start_field_name: "2024-03-01 02:00:00",
                self.date_stop_field_name: "2024-03-01 08:00:00",
            },
        )
        self.assert_not_replanned(
            self.pills2_0
            | self.pills2_1
            | self.pills2_2
            | self.pills2_3
            | self.pills2_9
            | self.pills2_10
            | self.pills2_11
            | self.pills2_12
            | self.pills2_13
            | self.pills2_14,
            self.initial_dates,
        )

        self.assertEqual(
            self.pills2_0[self.date_start_field_name],
            self.pills2_8[self.date_stop_field_name],
        )
        self.assertEqual(
            self.pills2_8[self.date_start_field_name],
            self.pills2_7[self.date_stop_field_name],
        )
        self.assertEqual(
            self.pills2_7[self.date_start_field_name],
            self.pills2_6[self.date_stop_field_name],
        )
        self.assertEqual(
            self.pills2_7[self.date_start_field_name],
            self.pills2_5[self.date_stop_field_name],
        )
        self.assertEqual(
            self.pills2_6[self.date_start_field_name],
            self.pills2_4[self.date_stop_field_name],
        )

    def test_dont_move_not_in_conflict(self):
        """
                                  ->[4]
                                  |
                                  ---------<-------
        [1]---------------------------->[2]->[3]--|

        When moving 3 before 4, 2 should also move to avoid creating conflicts, but 1
        should not be moved because with the new dates of 2 and 3, there is no
        conflict created.
        """
        self.pill_4.write(
            {
                self.date_start_field_name: datetime(2021, 4, 27, 8, 0),
                self.date_stop_field_name: datetime(2021, 4, 27, 12, 0),
            }
        )
        self.pill_2.write(
            {
                self.date_start_field_name: datetime(2021, 4, 27, 13, 0),
                self.date_stop_field_name: datetime(2021, 4, 27, 17, 0),
            }
        )
        self.pill_3.write(
            {
                self.date_start_field_name: datetime(2021, 4, 28, 13, 0),
                self.date_stop_field_name: datetime(2021, 4, 28, 18, 0),
            }
        )
        self.gantt_reschedule_consume_buffer(
            self.pill_3,
            {
                self.date_start_field_name: "2021-04-27 03:00:00",
                self.date_stop_field_name: "2021-04-27 08:00:00",
            },
        )
        self.assertEqual(
            self.pill_3[self.date_stop_field_name],
            self.pill_4[self.date_start_field_name],
            "3 moved before 4",
        )
        self.assertEqual(
            self.pill_2[self.date_stop_field_name],
            self.pill_3[self.date_start_field_name],
            "2 moved before 3",
        )
        self.assert_not_replanned(self.pill_1, self.initial_dates)
        self.assertEqual(
            self.pill_4[self.date_start_field_name],
            datetime(2021, 4, 27, 8, 0),
            "4 keeps the date this test gave it",
        )

    def test_reschedule_dates(self):
        pill = self.env["test.web.gantt.pill2"].create(
            {
                self.date_start_field_name: "2021-04-27",
                self.date_stop_field_name: "2021-04-27",
            }
        )

        self.env["test.web.gantt.pill2"].web_gantt_reschedule(
            {
                self.date_start_field_name: "2021-04-28",
                self.date_stop_field_name: "2021-04-28",
            },
            Base._WEB_GANTT_RESCHEDULE_CONSUME_BUFFER,
            pill.id,
            self.dependency_field_name,
            self.dependency_inverted_field_name,
            self.date_start_field_name,
            self.date_stop_field_name,
        )

        self.assertEqual(
            pill[self.date_stop_field_name],
            date(2021, 4, 28),
        )
        self.assertEqual(
            pill[self.date_start_field_name],
            date(2021, 4, 28),
        )

    def test_reschedule_reports_the_cycle_it_detected(self):
        """A dependency cycle names itself instead of raising a blank warning.

        ``_web_gantt_get_reschedule_message`` iterates the value under
        "errors", so a bare string is walked character by character and every
        character maps to no message: the user got a warning toast with an
        empty body.
        """
        self.pill_1.write({self.dependency_field_name: [Command.link(self.pill_4.id)]})

        res = self.gantt_reschedule_maintain_buffer(
            self.pill_1,
            {
                self.date_start_field_name: "2021-06-01 00:00:00",
                self.date_stop_field_name: "2021-06-01 10:00:00",
            },
        )

        self.assertEqual(res["type"], "warning")
        self.assertEqual(
            res["message"], "The dependencies are not valid, there is a cycle."
        )
        self.assert_not_replanned(
            self.pill_1 | self.pill_2 | self.pill_3 | self.pill_4, self.initial_dates
        )

    def test_reschedule_cascades_over_date_fields(self):
        """A gantt built on ``date`` fields reschedules its dependants too.

        The cascade converted every bound with ``astimezone``, which a
        ``datetime.date`` does not carry, so the first dependant raised
        TypeError. ``test_reschedule_dates`` did not catch it: a pill with no
        dependency never reaches the cascade.
        """
        Pill2 = self.env["test.web.gantt.pill2"]
        master = Pill2.create(
            {
                "name": "date master",
                self.date_start_field_name: date(2021, 4, 27),
                self.date_stop_field_name: date(2021, 4, 28),
            }
        )
        slave = Pill2.create(
            {
                "name": "date slave",
                self.date_start_field_name: date(2021, 4, 29),
                self.date_stop_field_name: date(2021, 4, 30),
                self.dependency_field_name: [Command.link(master.id)],
            }
        )

        res = Pill2.web_gantt_reschedule(
            {
                self.date_start_field_name: "2021-05-10",
                self.date_stop_field_name: "2021-05-11",
            },
            Base._WEB_GANTT_RESCHEDULE_CONSUME_BUFFER,
            master.id,
            self.dependency_field_name,
            self.dependency_inverted_field_name,
            self.date_start_field_name,
            self.date_stop_field_name,
        )

        self.assertEqual(res["type"], "success")
        self.assertEqual(master[self.date_start_field_name], date(2021, 5, 10))
        self.assertEqual(master[self.date_stop_field_name], date(2021, 5, 11))
        self.assertEqual(
            slave[self.date_start_field_name],
            master[self.date_stop_field_name],
            "the dependant moves behind its master rather than crashing",
        )
        self.assertEqual(
            res["old_vals_per_pill_id"][slave.id],
            {
                self.date_start_field_name: date(2021, 4, 29),
                self.date_stop_field_name: date(2021, 4, 30),
            },
            "the dependant's previous dates are recorded so undo can restore them",
        )

    def test_consume_buffer_skips_a_candidate_and_still_reaches_its_successor(self):
        self.pill_4[self.date_start_field_name] = self.pill_3_start_date + timedelta(
            hours=4
        )
        res = self.gantt_reschedule_consume_buffer(
            self.pill_1,
            {
                self.date_start_field_name: "2021-03-01 12:00:00",
                self.date_stop_field_name: "2021-03-01 20:00:00",
            },
        )
        self.assertEqual(res["type"], "success")
        self.assertEqual(
            self.pill_2[self.date_start_field_name],
            self.pill_2_start_date,
            "Pill 2 was not in conflict and stays where it was",
        )
        self.assertEqual(
            self.pill_4[self.date_start_field_name],
            self.pill_3[self.date_stop_field_name],
            "Pill 4 is pushed to the end of Pill 3, whose own dates did not move",
        )

    def test_maintain_buffer_ignores_a_dependent_without_dates(self):
        undated = self.create_pill("Undated", False, False, [self.pill_1.id])
        res = self.gantt_reschedule_maintain_buffer(
            self.pill_1,
            {
                self.date_start_field_name: "2021-06-01 00:00:00",
                self.date_stop_field_name: "2021-06-01 10:00:00",
            },
        )
        self.assertEqual(res["type"], "success")
        self.assertFalse(undated[self.date_start_field_name])
        self.assertEqual(
            self.pill_1[self.date_stop_field_name] + timedelta(seconds=self.buffer12),
            self.pill_2[self.date_start_field_name],
        )

    def test_consume_buffer_backward_skips_a_candidate_and_still_reaches_its_predecessor(
        self,
    ):
        # Pill 1 already overlaps pill 2 (pre-existing conflict); pill 3 is not
        # in conflict once pill 4 moves back, so it is skipped and never pushes
        # pill 2, which then indexes the bound dict without a key.
        self.pill_1[self.date_stop_field_name] = self.pill_2_start_date + timedelta(
            hours=4
        )
        res = self.gantt_reschedule_consume_buffer(
            self.pill_4,
            {
                self.date_start_field_name: "2021-03-03 20:00:00",
                self.date_stop_field_name: "2021-03-04 04:00:00",
            },
        )
        self.assertEqual(res["type"], "success", res)
        self.assertEqual(
            self.pill_3[self.date_start_field_name],
            self.pill_3_start_date,
            "Pill 3 was not in conflict and stays where it was",
        )
        self.assertEqual(
            self.pill_1[self.date_stop_field_name],
            self.pill_2[self.date_start_field_name],
            "Pill 1 is pulled to the start of Pill 2, whose own dates did not move",
        )

    def test_maintain_buffer_backward_ignores_a_predecessor_without_dates(self):
        undated = self.create_pill("Undated", False, False)
        self.pill_4.write({self.dependency_field_name: [Command.link(undated.id)]})
        res = self.gantt_reschedule_maintain_buffer(
            self.pill_4,
            {
                self.date_start_field_name: "2021-02-20 08:00:00",
                self.date_stop_field_name: "2021-02-20 16:00:00",
            },
        )
        self.assertEqual(res["type"], "success", res)
        self.assertFalse(undated[self.date_stop_field_name])
        self.assertEqual(
            self.pill_3[self.date_stop_field_name] + timedelta(seconds=self.buffer34),
            self.pill_4[self.date_start_field_name],
        )

    def test_reschedule_refuses_a_field_name_of_the_wrong_kind(self):
        with self.assertRaisesRegex(UserError, "not a date / datetime field"):
            self.TestWebGanttPill.web_gantt_reschedule(
                {self.date_start_field_name: "2021-06-01 00:00:00"},
                Base._WEB_GANTT_RESCHEDULE_CONSUME_BUFFER,
                self.pill_1.id,
                self.dependency_field_name,
                self.dependency_inverted_field_name,
                "name",
                self.date_stop_field_name,
            )
        with self.assertRaisesRegex(UserError, "not a many2many / one2many field"):
            self.TestWebGanttPill.web_gantt_reschedule(
                {self.date_start_field_name: "2021-06-01 00:00:00"},
                Base._WEB_GANTT_RESCHEDULE_CONSUME_BUFFER,
                self.pill_1.id,
                "parent_id",
                self.dependency_inverted_field_name,
                self.date_start_field_name,
                self.date_stop_field_name,
            )

    def test_a_dependent_the_user_may_not_write_is_a_notification(self):
        original_write = type(self.pill_3).write
        forbidden = self.pill_3.id

        def write(records, vals):
            if forbidden in records.ids and self.date_start_field_name in vals:
                raise AccessError("no way")
            return original_write(records, vals)

        with patch.object(type(self.pill_3), "write", write):
            res = self.gantt_reschedule_consume_buffer(
                self.pill_1,
                {
                    self.date_start_field_name: "2021-06-01 00:00:00",
                    self.date_stop_field_name: "2021-06-01 10:00:00",
                },
            )
        self.assertEqual(res["type"], "warning")
        self.assertEqual(res["message"], "no way")
        self.assert_not_replanned(self.pills_topo_order, self.initial_dates)

    def test_placing_a_record_without_a_start_reschedules_forward(self):
        undated = self.create_pill("Undated", False, False)
        self.pill_1.write({self.dependency_field_name: [Command.link(undated.id)]})
        res = self.gantt_reschedule_consume_buffer(
            undated,
            {
                self.date_start_field_name: "2021-03-01 12:00:00",
                self.date_stop_field_name: "2021-03-01 20:00:00",
            },
        )
        self.assertEqual(res["type"], "success", res)
        self.assertEqual(
            self.pill_1[self.date_start_field_name],
            undated[self.date_stop_field_name],
            "Pill 1 is pushed to the end of the pill placed before it",
        )

    def test_a_past_error_mid_cascade_rolls_every_write_back(self):
        # Pill 4 moves to the first day of 2021 (today): pill 3 fits before it
        # and is written, pill 2 would have to end before 04:00 and lands in
        # 2020 -- refused, and the savepoint must undo pill 3 and pill 4 both.
        res = self.gantt_reschedule_consume_buffer(
            self.pill_4,
            {
                self.date_start_field_name: "2021-01-01 12:00:00",
                self.date_stop_field_name: "2021-01-01 20:00:00",
            },
        )
        self.assert_old_pills_vals(
            res,
            "warning",
            "Pill 2 cannot be scheduled in the past",
            self.env["test.web.gantt.pill"],
            self.initial_dates,
        )
        self.assert_not_replanned(self.pills_topo_order, self.initial_dates)

    def test_a_start_a_few_seconds_in_the_past_is_still_accepted(self):
        # The 30s epsilon: the first valid interval can be "now" and drift
        # below now() by the time the comparison runs.
        now = datetime(2021, 1, 1)
        self.assertTrue(
            self.pill_1._web_gantt_reschedule_write_new_dates(
                now - timedelta(seconds=20),
                now + timedelta(hours=8),
                self.date_start_field_name,
                self.date_stop_field_name,
            )
        )
        self.assertFalse(
            self.pill_1._web_gantt_reschedule_write_new_dates(
                now - timedelta(seconds=40),
                now + timedelta(hours=8),
                self.date_start_field_name,
                self.date_stop_field_name,
            )
        )

    def test_rollback_takes_the_payload_as_the_client_sends_it(self):
        # JSON round-trips the ids to strings and the datetimes to strings.
        moved = self.pill_1 | self.pill_2
        payload = {
            str(self.pill_1.id): {
                self.date_start_field_name: "2021-03-01 08:00:00",
                self.date_stop_field_name: "2021-03-01 16:00:00",
            },
            str(self.pill_2.id): {
                self.date_start_field_name: "2021-03-02 08:00:00",
                self.date_stop_field_name: "2021-03-02 16:00:00",
            },
        }
        moved.write({self.date_start_field_name: datetime(2021, 6, 1, 8)})
        moved.action_rollback_scheduling(payload)
        self.assert_not_replanned(moved, self.initial_dates)
