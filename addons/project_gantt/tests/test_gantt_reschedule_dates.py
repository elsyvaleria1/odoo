from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo.fields import Command
from odoo.tests.common import freeze_time, tagged, users

from .gantt_reschedule_dates_common import (
    ProjectGanttRescheduleCommon,
    fake_now,
)


@tagged("gantt_reschedule", "post_install", "-at_install")
@freeze_time(fake_now)
class TestGanttRescheduleOnTasks(ProjectGanttRescheduleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.task_1_date_deadline -= timedelta(hours=2)
        cls.task_1.write({"date_end": cls.task_1_date_deadline, "planned_hours": 1})

    def test_gantt_reschedule_date_not_active(self):

        def test_task_3_dates_unchanged(
            task_1_new_planned_dates, failed_message, domain_force=False, **context
        ):
            task_1 = (
                self.task_1.with_context(context)
                if domain_force
                else self.task_1.with_context(**context)
            )
            self.gantt_reschedule_consume_buffer(self.task_1, task_1_new_planned_dates)
            self.assertEqual(
                self.task_3_planned_date_begin,
                self.task_3.date_start,
                failed_message,
            )
            self.assertEqual(
                self.task_3_date_deadline, self.task_3.date_end, failed_message
            )
            task_1.write(
                {
                    "date_start": self.task_1_planned_date_begin,
                    "date_end": self.task_1_date_deadline,
                }
            )

        self.task_4.predecessor_ids = [Command.clear()]

        failed_message = (
            "The auto shift date feature should not be triggered after having moved a task that "
            "does not have a project_id."
        )
        project_id = self.task_1.project_id
        self.task_1.write({"project_id": False})
        test_task_3_dates_unchanged(
            self.task_1_date_gantt_reschedule_trigger(), failed_message
        )
        self.task_1.write({"project_id": project_id.id})

        failed_message = (
            "The auto shift date feature should not be triggered on tasks (predecessor_ids/successor_ids) "
            "that do have a project_id."
        )
        project_id = self.task_3.project_id
        self.task_3.write({"project_id": False})
        test_task_3_dates_unchanged(
            self.task_1_date_gantt_reschedule_trigger(), failed_message
        )
        self.task_3.write({"project_id": project_id.id})

        with freeze_time(
            self.task_1_no_date_gantt_reschedule_trigger()["date_start"]
            + relativedelta(weeks=1)
        ):
            failed_message = (
                "The auto shift date feature should not trigger any changes when the new planned_date "
                "is prior to the current datetime."
            )
            test_task_3_dates_unchanged(
                self.task_1_date_gantt_reschedule_trigger(), failed_message
            )

    def test_gantt_reschedule_forward_dependent_task_consume_and_maintain_buffer(self):

        moved_tasks = self.task_3 | self.task_1
        not_moved_tasks = self.task_4 | self.task_5 | self.task_6
        old_vals = {task.name: (task.date_start, task.date_end) for task in moved_tasks}

        res = self.gantt_reschedule_consume_buffer(
            self.task_1, self.task_1_date_gantt_reschedule_trigger()
        )
        self.assert_old_tasks_vals(
            res, "success", "Tasks rescheduled", moved_tasks, old_vals
        )

        failed_message = (
            "The auto shift date feature should move forward a dependent tasks."
        )
        self.assertEqual(
            self.task_3.date_start, datetime(2021, 6, 24, 14), failed_message
        )
        self.assertEqual(
            self.task_3.date_end, datetime(2021, 6, 24, 16), failed_message
        )
        self.assertEqual(
            self.task_1.date_start, datetime(2021, 6, 24, 13), failed_message
        )
        self.assertEqual(
            self.task_1.date_end, datetime(2021, 6, 24, 14), failed_message
        )
        self.assert_task_not_replanned(
            not_moved_tasks, self.project_pigs_intial_dates()
        )

        moved_tasks.action_rollback_scheduling(res["old_vals_per_pill_id"])
        self.assertEqual(
            (self.task_3.date_start, self.task_3.date_end),
            old_vals[self.task_3.name],
        )
        self.assertEqual(
            (self.task_1.date_start, self.task_1.date_end),
            old_vals[self.task_1.name],
        )

        moved_tasks |= not_moved_tasks
        for task in not_moved_tasks:
            old_vals[task.name] = (task.date_start, task.date_end)

        res = self.gantt_reschedule_maintain_buffer(
            self.task_1, self.task_1_date_gantt_reschedule_trigger()
        )
        self.assert_old_tasks_vals(
            res, "success", "Tasks rescheduled", moved_tasks, old_vals
        )

        self.assertEqual(
            self.task_1.date_start, datetime(2021, 6, 24, 13), failed_message
        )
        self.assertEqual(
            self.task_1.date_end, datetime(2021, 6, 24, 14), failed_message
        )
        self.assertEqual(
            self.task_3.date_start,
            datetime(2021, 6, 24, 16),
            failed_message
            + "tasks 3 should start after buffer = 2 hours after the end of task 1",
        )
        self.assertEqual(
            self.task_3.date_end,
            datetime(2021, 6, 25, 9),
            failed_message
            + "tasks 3 should start after buffer = 2 hours after the end of task 1",
        )

        self.assertEqual(
            self.task_4.date_start,
            datetime(2021, 8, 2, 9),
            failed_message
            + """
            buffer between task 3 and 4 = 32H
            we need to wait 31h in month 6 (7 hours on day 25 and 24 Hours on the last week)
            month 7 is off for the company
            1 hours on monday 02/08
        """,
        )
        self.assertEqual(
            self.task_4.date_end,
            self.task_5.date_start,
            failed_message + "buffer = 0 between task 4 and 5 as month 07 was off",
        )
        self.assertEqual(
            self.task_5.date_end,
            self.task_6.date_start,
            failed_message + "buffer = 0 between task 5 and 6",
        )

    def test_gantt_reschedule_backward_dependent_task_consume_and_maintain_buffer(self):
        moved_tasks = self.task_6 | self.task_5 | self.task_4
        not_moved_tasks = self.task_3 | self.task_1
        old_vals = {task.name: (task.date_start, task.date_end) for task in moved_tasks}

        task_6_vals = {
            "date_start": "2021-08-03 08:00:00",
            "date_end": "2021-08-03 17:00:00",
        }

        res = self.gantt_reschedule_consume_buffer(self.task_6, task_6_vals)
        self.assert_old_tasks_vals(
            res, "success", "Tasks rescheduled", moved_tasks, old_vals
        )

        failed_message = (
            "The auto shift date feature should move forward a dependent tasks."
        )
        self.assertEqual(
            self.task_6.date_start, datetime(2021, 8, 3, 8), failed_message
        )
        self.assertEqual(self.task_6.date_end, datetime(2021, 8, 3, 17), failed_message)
        self.assertEqual(
            self.task_5.date_start, datetime(2021, 6, 30, 8), failed_message
        )
        self.assertEqual(self.task_5.date_end, datetime(2021, 8, 2, 17), failed_message)
        self.assert_task_not_replanned(
            not_moved_tasks, self.project_pigs_intial_dates()
        )

        moved_tasks.action_rollback_scheduling(res["old_vals_per_pill_id"])
        for task in moved_tasks:
            self.assertEqual((task.date_start, task.date_end), old_vals[task.name])

        """
            2- maintain buffer

            buffer(5, 6) = 0
            buffer(4, 5) = 0
            buffer(4, 3) = 32H => as task 4 were moved day in the past, task 3 moved also 1 day in the past to keep the buffer
            buffer(1, 3) = 2H => task 1 will also follow by moving one day in the past to keep the buffer

            INFO: it's one day in the back by chance because it's still in a valid period (task 5 and task 6 are counter examples)

            ┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐
            │ Task 1  │ -->  │ Task 3  │ -->  │ Task 4  │ -->  │ Task 5  │ -->  │ Task 6  │
            │         │      │         │      │         │      │30/06 8H │      │         │
            │ 23/06   │      │ 23/06   │      │ 29/06   │      │   ->    │      │ 03/08   │
            │ 9H > 10H│      │13H > 15H│      │15H > 17H│      │02/08 17H│      │ 8H->17H │
            └─────────┘      └─────────┘      └─────────┘      └─────────┘      └─────────┘
        """
        moved_tasks |= not_moved_tasks
        for task in not_moved_tasks:
            old_vals[task.name] = (task.date_start, task.date_end)

        res = self.gantt_reschedule_maintain_buffer(self.task_6, task_6_vals)
        self.assert_old_tasks_vals(
            res, "success", "Tasks rescheduled", moved_tasks, old_vals
        )

        self.assertEqual(
            self.task_6.date_start, datetime(2021, 8, 3, 8), failed_message
        )
        self.assertEqual(self.task_6.date_end, datetime(2021, 8, 3, 17), failed_message)
        self.assertEqual(
            self.task_5.date_start, datetime(2021, 6, 30, 8), failed_message
        )
        self.assertEqual(
            self.task_5.date_end,
            datetime(2021, 8, 2, 17),
            failed_message + "buffer = 0 between task 5 and 6, and month 07 is off",
        )

        for task in self.task_1 | self.task_3 | self.task_4:
            self.assertEqual(
                task.date_start,
                old_vals[task.name][0] + timedelta(days=-1),
                failed_message,
            )
            self.assertEqual(
                task.date_end,
                old_vals[task.name][1] + timedelta(days=-1),
                failed_message,
            )

    def test_gantt_reschedule_forward_dependent_task_maintain_buffer_with_missing_start_date_on_task(
        self,
    ):
        self.task_3.date_start = False
        task3_date_deadline = self.task_3.date_end
        res = self.gantt_reschedule_maintain_buffer(
            self.task_1, self.task_1_date_gantt_reschedule_trigger()
        )
        self.assertEqual(self.task_1.date_start, datetime(2021, 6, 24, 13))
        self.assertEqual(self.task_1.date_end, datetime(2021, 6, 24, 14))
        self.assertFalse(self.task_3.date_start)
        self.assertEqual(self.task_3.date_end, task3_date_deadline)
        self.assert_task_not_replanned(
            self.task_4 | self.task_5 | self.task_6, self.project_pigs_intial_dates()
        )
        self.assertEqual(res["message"], "Tasks rescheduled")

    def test_gantt_reschedule_backward_dependent_task_maintain_buffer_with_missing_date_deadline_on_task(
        self,
    ):
        self.task_4.date_end = False
        task4_date_begin = self.task_4.date_start
        task_6_vals = {
            "date_start": "2021-08-03 08:00:00",
            "date_end": "2021-08-03 17:00:00",
        }
        res = self.gantt_reschedule_maintain_buffer(self.task_6, task_6_vals)
        self.assertEqual(self.task_6.date_start, datetime(2021, 8, 3, 8))
        self.assertEqual(self.task_6.date_end, datetime(2021, 8, 3, 17))
        self.assertEqual(self.task_5.date_start, datetime(2021, 6, 30, 8))
        self.assertEqual(self.task_5.date_end, datetime(2021, 8, 2, 17))
        self.assertFalse(self.task_4.date_end)
        self.assertEqual(self.task_4.date_start, task4_date_begin)
        self.assert_task_not_replanned(
            self.task_3 | self.task_1, self.project_pigs_intial_dates()
        )
        self.assertEqual(res["message"], "Tasks rescheduled")

    @users("admin")
    def test_gantt_reschedule_with_planned_hours(self):
        self.task_3.planned_hours = 8
        self.gantt_reschedule_consume_buffer(
            self.task_1, self.task_1_date_gantt_reschedule_trigger()
        )
        failed_message = (
            "The auto shift date feature should take the allocated_hours into account and update the"
            "date_end accordingly when moving a task forward."
        )
        self.assertEqual(
            (self.task_3.date_start, self.task_3.date_end),
            (datetime(2021, 6, 24, 14, 0), datetime(2021, 6, 25, 14, 0)),
            failed_message + "8 hours between dates",
        )

    @users("admin")
    def test_gantt_reschedule_without_allocated_hours(self):
        self.task_3.write(
            {
                "planned_hours": 0,
            }
        )
        self.gantt_reschedule_consume_buffer(
            self.task_1, self.task_1_date_gantt_reschedule_trigger()
        )
        failed_message = (
            "The auto shift date feature should take the allocated_hours into account and update the"
            "date_end accordingly when moving a task forward."
        )
        self.assertEqual(
            (self.task_3.date_start, self.task_3.date_end),
            (datetime(2021, 6, 24, 14, 0), datetime(2021, 6, 24, 16, 0)),
            failed_message + "2 hours between dates",
        )

    def test_gantt_reschedule_project_user(self):
        new_task_6_planned_date_begin = self.task_5_planned_date_begin + timedelta(
            hours=1
        )
        self.gantt_reschedule_consume_buffer(
            self.task_6,
            {
                "date_start": new_task_6_planned_date_begin.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "date_end": (
                    new_task_6_planned_date_begin
                    + (self.task_6_date_deadline - self.task_6_planned_date_begin)
                ).strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        failed_message = (
            "The auto shift date feature should handle correctly dependencies cascades."
        )
        self.assertEqual(
            self.task_5.date_end, new_task_6_planned_date_begin, failed_message
        )
        self.assertEqual(
            self.task_5.date_start,
            datetime(year=2021, month=6, day=29, hour=9),
            failed_message,
        )
        self.assertEqual(self.task_4.date_end, self.task_5.date_start, failed_message)
        self.assertEqual(
            self.task_4.date_start,
            datetime(year=2021, month=6, day=28, hour=16),
            failed_message,
        )

    @users("admin")
    def test_project2_reschedule_cascading_forward(self):
        self.project2_task_1.successor_ids = self.project2_task_1.successor_ids.sorted(
            key=lambda t: t.name, reverse=True
        )
        self.gantt_reschedule_consume_buffer(
            self.project2_task_0,
            {
                "date_start": "2024-03-18 08:00:00",
                "date_end": "2024-03-18 12:00:00",
            },
        )

        self.assert_task_not_replanned(
            self.project2_task_4
            | self.project2_task_5
            | self.project2_task_6
            | self.project2_task_7
            | self.project2_task_8
            | self.project2_task_9
            | self.project2_task_10
            | self.project2_task_11
            | self.project2_task_12
            | self.project2_task_13
            | self.project2_task_14,
            self.initial_dates,
        )

        self.assert_new_dates(
            self.project2_task_0,
            datetime(year=2024, month=3, day=18, hour=8),
            datetime(year=2024, month=3, day=18, hour=12),
        )

        self.assert_new_dates(
            self.project2_task_1,
            datetime(year=2024, month=3, day=18, hour=13),
            datetime(year=2024, month=3, day=18, hour=17),
            "task 1 duration = 4 Hours. 4 hours will be planned on 18/03/2024 from 13H to 17H",
        )

        self.assert_new_dates(
            self.project2_task_2,
            datetime(year=2024, month=3, day=19, hour=8),
            datetime(year=2024, month=3, day=19, hour=10),
            "task 2 duration = 2 Hours. 2 hours will be planned on 19/03/2024 from 8H to 10H",
        )

        self.assert_new_dates(
            self.project2_task_3,
            datetime(year=2024, month=3, day=19, hour=10),
            datetime(year=2024, month=3, day=19, hour=16),
            "task 3 duration = 5 Hours. 5 hours will be planned on 19/03/2024 from 10H to 16H",
        )

    @users("admin")
    def test_project2_reschedule_cascading_backward(self):
        self.project2_task_7.predecessor_ids = (
            self.project2_task_7.predecessor_ids.sorted(key=lambda t: t.name)
        )
        self.gantt_reschedule_consume_buffer(
            self.project2_task_8,
            {
                "date_start": "2024-02-27 10:00:00",
                "date_end": "2024-02-29 17:00:00",
            },
        )
        self.assert_task_not_replanned(
            self.project2_task_0
            | self.project2_task_1
            | self.project2_task_2
            | self.project2_task_3
            | self.project2_task_9
            | self.project2_task_10
            | self.project2_task_11
            | self.project2_task_12
            | self.project2_task_13
            | self.project2_task_14,
            self.initial_dates,
        )

        self.assert_new_dates(
            self.project2_task_8,
            datetime(year=2024, month=2, day=27, hour=10),
            datetime(year=2024, month=2, day=29, hour=17),
        )
        self.assert_new_dates(
            self.project2_task_7,
            datetime(year=2024, month=2, day=26, hour=15),
            datetime(year=2024, month=2, day=27, hour=10),
            """
                task 7 duration = 4 Hours.
                2 hours available on 27/02/2024 from 8H to 10H.
                2 hours available on 26/02/2024 from 15H to 17H.
            """,
        )

        self.assert_new_dates(
            self.project2_task_6,
            datetime(year=2024, month=2, day=21, hour=13),
            datetime(year=2024, month=2, day=23, hour=17),
            """
                task 6 duration = 20 Hours.
                no hours available in 26/02/2024 as task 7 was planned from 15H to 17H
                and task 14 planned from 8H to 15H
                16 hours will be planned on 22/02 and 23/02
                4 hours will be planned on 21/02 from 13H to 17H
            """,
        )

        self.assert_new_dates(
            self.project2_task_4,
            datetime(year=2024, month=2, day=19, hour=13),
            datetime(year=2024, month=2, day=21, hour=12),
            """
                task 4 duration = 16 Hours
                4 Hours on 19/02
                8 hours on 20/02
                4 hours on 21/02 from 8H to 12H
            """,
        )

        self.assert_new_dates(
            self.project2_task_5,
            datetime(year=2024, month=2, day=15, hour=13),
            datetime(year=2024, month=2, day=19, hour=12),
            """
                task 5 duration = 16 Hours.
                4 hours will be planned on 19/02
                8 hours will be planned on 16/02
                4 hours will be planned on 15 from 13H to 17H
            """,
        )

    @users("admin")
    def test_project2_reschedule_cascading_backward_no_planning_in_the_past(self):
        self.project2_task_0.date_start = datetime(year=2021, month=4, day=7, hour=8)
        res = self.gantt_reschedule_consume_buffer(
            self.project2_task_8,
            {
                "date_start": "2021-04-05 11:00:00",
                "date_end": "2021-04-06 17:00:00",
            },
        )
        moved_tasks = (
            self.project2_task_8
            + self.project2_task_7
            + self.project2_task_6
            + self.project2_task_5
            + self.project2_task_4
        )
        self.assert_old_tasks_vals(
            res,
            "info",
            "Some tasks were scheduled concurrently, resulting in a conflict due to the limited availability of the assignees. The planned dates for these tasks may not align with their allocated hours.",
            moved_tasks,
            self.initial_dates,
        )

        self.assert_new_dates(
            self.project2_task_8,
            datetime(year=2021, month=4, day=5, hour=11),
            datetime(year=2021, month=4, day=6, hour=17),
        )

        self.assert_new_dates(
            self.project2_task_7,
            datetime(year=2021, month=4, day=2, hour=16),
            datetime(year=2021, month=4, day=5, hour=11),
            """
                task 7 duration = 4 Hours.
                5 hours to plan on 05/04 from 8H to 11H
                1 hour to plan on 02/04 from 16H to 17H
            """,
        )

        self.assert_new_dates(
            self.project2_task_5,
            datetime(year=2021, month=4, day=1, hour=8),
            datetime(year=2021, month=4, day=2, hour=17),
            """
                task 5 duration = 16 Hours.
                No available slot to plan it, so it will be planned in conflict starting from the first available slot 01/04/2021
            """,
        )

        self.assert_new_dates(
            self.project2_task_6,
            datetime(year=2021, month=4, day=1, hour=8),
            datetime(year=2021, month=4, day=5, hour=12),
            """
                task 6 duration = 20 Hours.
                No available slot to plan it, so it will be planned in conflict starting from the first available slot 01/04/2021
            """,
        )

        self.assert_new_dates(
            self.project2_task_4,
            datetime(year=2021, month=4, day=1, hour=8),
            datetime(year=2021, month=4, day=2, hour=17),
            """
                task 4 duration = 16 Hours.
                No available slot to plan it, so it will be planned in conflict starting from the first available slot 01/04/2021
            """,
        )

        moved_tasks.action_rollback_scheduling(res["old_vals_per_pill_id"])
        self.assert_task_not_replanned(moved_tasks, self.initial_dates)

    @users("admin")
    def test_compute_task_duration(self):
        durations = self.project2_task_6._get_tasks_durations(
            self.user_projectuser, "date_start", "date_end"
        )
        self.assertEqual(durations[self.project2_task_6.id], 20 * 3600)

    @users("admin")
    def test_backward_cross_project(self):
        self.project2_task_7.successor_ids = self.project2_task_7.successor_ids.sorted(
            key=lambda t: t.name
        )
        (
            self.project2_task_0 + self.project2_task_4 + self.project2_task_7
        ).project_id = self.project_pigs.id
        self.gantt_reschedule_consume_buffer(
            self.project2_task_8,
            {
                "date_start": "2024-02-27 10:00:00",
                "date_end": "2024-02-29 17:00:00",
            },
        )
        self.assert_task_not_replanned(
            self.project2_task_0
            | self.project2_task_1
            | self.project2_task_2
            | self.project2_task_3
            | self.project2_task_9
            | self.project2_task_10
            | self.project2_task_11
            | self.project2_task_12
            | self.project2_task_13
            | self.project2_task_14,
            self.initial_dates,
        )

        self.assert_new_dates(
            self.project2_task_8,
            datetime(year=2024, month=2, day=27, hour=10),
            datetime(year=2024, month=2, day=29, hour=17),
            """
                task 8 duration = 13 Hours.
                Only 2 hours available on 29/02/2024 because task 12 and 13 are planned from 9H to 16H.
                Only 5 hours available on 28/02/2024 because task 11 is planned from 8H to 11H.
                The remaining 6 hours will be planned in 27/02/2024 from 10H
            """,
        )
        self.assert_new_dates(
            self.project2_task_7,
            datetime(year=2024, month=2, day=26, hour=15),
            datetime(year=2024, month=2, day=27, hour=10),
            """
                task 8 duration = 4 Hours.
                2 hours available on 27/02/2024 from 8H to 10H.
                2 hours available on 26/02/2024 from 15H to 17H.
            """,
        )

        self.assert_new_dates(
            self.project2_task_5,
            datetime(year=2024, month=2, day=15, hour=13),
            datetime(year=2024, month=2, day=19, hour=12),
            """
                task 5 duration = 16 Hours.
                day 17/02 and 18/02 are weekend
                4 hours planned on day 15/02
                8 hours planned on day 16/02
                4 hours planned on day 19/02
            """,
        )

        self.assert_new_dates(
            self.project2_task_6,
            datetime(year=2024, month=2, day=21, hour=13),
            datetime(year=2024, month=2, day=23, hour=17),
            """
                task 6 duration = 20 Hours.
                4 Hours on 21/02, 16 Hours on 22/02 and 23/02
            """,
        )

        self.assert_new_dates(
            self.project2_task_4,
            datetime(year=2024, month=2, day=19, hour=13),
            datetime(year=2024, month=2, day=21, hour=12),
            """
                task 4 duration = 16 Hours
                4 Hours on 19/02
                8 hours on 20/02
                4 hours on 21/02 from 8H to 12H
            """,
        )

    def test_move_forward_with_multi_users(self):
        self.project2_task_8.write(
            {
                "predecessor_ids": [Command.unlink(self.project2_task_7.id)],
            }
        )
        (self.project2_task_4 + self.project2_task_6).write(
            {
                "user_ids": [self.user2.id, self.user1.id],
            }
        )

        (self.project2_task_9 + self.project2_task_10).write(
            {
                "user_ids": [self.user1.id],
            }
        )

        self.project2_task_2.write(
            {
                "successor_ids": [Command.link(self.project2_task_5.id)],
                "predecessor_ids": [
                    Command.link(self.project2_task_4.id),
                    Command.unlink(self.project2_task_7.id),
                ],
            }
        )

        self.project2_task_5.write(
            {"successor_ids": [Command.unlink(self.project2_task_7.id)]}
        )

        self.project2_task_1.write(
            {"successor_ids": [Command.link(self.project2_task_4.id)]}
        )

        res = self.gantt_reschedule_consume_buffer(
            self.project2_task_0,
            {
                "date_start": "2024-03-18 08:00:00",
                "date_end": "2024-03-18 12:00:00",
            },
        )
        moved_tasks = (
            self.project2.task_ids
            - self.project2_task_8
            - self.project2_task_12
            - self.project2_task_13
            - self.project2_task_14
            - self.project2_task_11
        )
        self.assert_old_tasks_vals(
            res, "success", "Tasks rescheduled", moved_tasks, self.initial_dates
        )
        self.assert_new_dates(
            self.project2_task_0,
            datetime(year=2024, month=3, day=18, hour=8),
            datetime(year=2024, month=3, day=18, hour=12),
        )

        self.assert_new_dates(
            self.project2_task_1,
            datetime(year=2024, month=3, day=18, hour=13),
            datetime(year=2024, month=3, day=18, hour=17),
        )

        self.assert_new_dates(
            self.project2_task_3,
            datetime(year=2024, month=3, day=19, hour=8),
            datetime(year=2024, month=3, day=19, hour=14),
        )

        self.assert_new_dates(
            self.project2_task_4,
            datetime(year=2024, month=3, day=19, hour=8),
            datetime(year=2024, month=3, day=20, hour=17),
        )

        self.assert_new_dates(
            self.project2_task_2,
            datetime(year=2024, month=3, day=21, hour=8),
            datetime(year=2024, month=3, day=21, hour=10),
        )

        self.assert_new_dates(
            self.project2_task_6,
            datetime(year=2024, month=3, day=21, hour=8),
            datetime(year=2024, month=3, day=25, hour=12),
            "allocated_hours = 20",
        )

        self.assert_new_dates(
            self.project2_task_7,
            datetime(year=2024, month=3, day=25, hour=13),
            datetime(year=2024, month=3, day=25, hour=17),
        )

        self.assert_new_dates(
            self.project2_task_5,
            datetime(year=2024, month=3, day=21, hour=10),
            datetime(year=2024, month=3, day=25, hour=10),
        )

        self.assert_new_dates(
            self.project2_task_9,
            datetime(year=2024, month=3, day=25, hour=13),
            datetime(year=2024, month=3, day=25, hour=17),
            """
                task 9 should start after task 5 which is its blocking task and after task 6
                as user Raouf 2 was busy doing it.
            """,
        )

        self.assert_new_dates(
            self.project2_task_10,
            datetime(year=2024, month=3, day=26, hour=8),
            datetime(year=2024, month=3, day=26, hour=12),
        )

        moved_tasks.action_rollback_scheduling(res["old_vals_per_pill_id"])
        self.assert_task_not_replanned(moved_tasks, self.initial_dates)

    def test_move_backward_with_multi_users(self):
        self.project2_task_7.successor_ids = self.project2_task_7.successor_ids.sorted(
            key=lambda t: t.name
        )
        self.project2_task_8.write(
            {
                "predecessor_ids": [
                    Command.link(self.project2_task_10.id),
                    Command.link(self.project2_task_7.id),
                ],
                "successor_ids": [
                    Command.unlink(self.project2_task_0.id),
                    Command.link(self.project2_task_13.id),
                ],
            }
        )

        (self.project2_task_4 + self.project2_task_6).write(
            {
                "user_ids": [self.user2.id, self.user1.id],
            }
        )

        (self.project2_task_9 + self.project2_task_10).write(
            {
                "user_ids": [self.user1.id],
            }
        )

        self.project2_task_2.write(
            {
                "successor_ids": [Command.link(self.project2_task_5.id)],
                "predecessor_ids": [
                    Command.unlink(self.project2_task_7.id),
                    Command.link(self.project2_task_4.id),
                ],
            }
        )

        self.project2_task_5.write(
            {"successor_ids": [Command.unlink(self.project2_task_7.id)]}
        )

        self.project2_task_1.write(
            {"successor_ids": [Command.link(self.project2_task_4.id)]}
        )

        res = self.gantt_reschedule_consume_buffer(
            self.project2_task_8,
            {
                "date_start": "2024-02-27 09:00:00",
                "date_end": "2024-02-29 09:00:00",
            },
        )
        moved_tasks = (
            self.project2.task_ids
            - self.project2_task_13
            - self.project2_task_3
            - self.project2_task_11
            - self.project2_task_14
            - self.project2_task_12
        )
        self.assert_old_tasks_vals(
            res, "success", "Tasks rescheduled", moved_tasks, self.initial_dates
        )

        self.assert_new_dates(
            self.project2_task_0,
            datetime(year=2024, month=2, day=14, hour=9),
            datetime(year=2024, month=2, day=14, hour=14),
        )

        self.assert_new_dates(
            self.project2_task_1,
            datetime(year=2024, month=2, day=14, hour=14),
            datetime(year=2024, month=2, day=15, hour=9),
        )

        self.assert_new_dates(
            self.project2_task_4,
            datetime(year=2024, month=2, day=15, hour=9),
            datetime(year=2024, month=2, day=19, hour=9),
        )

        self.assert_new_dates(
            self.project2_task_2,
            datetime(year=2024, month=2, day=21, hour=15),
            datetime(year=2024, month=2, day=21, hour=17),
        )

        self.assert_new_dates(
            self.project2_task_6,
            datetime(year=2024, month=2, day=19, hour=9),
            datetime(year=2024, month=2, day=21, hour=14),
        )

        self.assert_new_dates(
            self.project2_task_7,
            datetime(year=2024, month=2, day=21, hour=14),
            datetime(year=2024, month=2, day=27, hour=9),
        )

        self.assert_new_dates(
            self.project2_task_5,
            datetime(year=2024, month=2, day=22, hour=8),
            datetime(year=2024, month=2, day=23, hour=17),
        )

        self.assert_new_dates(
            self.project2_task_9,
            datetime(year=2024, month=2, day=26, hour=9),
            datetime(year=2024, month=2, day=26, hour=14),
        )

        self.assert_new_dates(
            self.project2_task_10,
            datetime(year=2024, month=2, day=26, hour=14),
            datetime(year=2024, month=2, day=27, hour=9),
        )

        self.assert_new_dates(
            self.project2_task_8,
            datetime(year=2024, month=2, day=27, hour=9),
            datetime(year=2024, month=2, day=29, hour=9),
        )
        moved_tasks.action_rollback_scheduling(res["old_vals_per_pill_id"])
        self.assert_task_not_replanned(moved_tasks, self.initial_dates)

    def test_web_gantt_write(self):
        users = self.user_projectuser + self.user_projectmanager
        self.task_1.write({"user_ids": users.ids})
        self.task_2.write({"user_ids": self.user_projectuser.ids})
        tasks = self.task_1 + self.task_2
        tasks.web_gantt_write({"user_ids": self.user_projectmanager.ids})
        self.assertEqual(
            self.task_1.user_ids,
            users,
            "The assignees set on Task 1 should remain the same if the new assigne was in fact already in the assigness of the task.",
        )
        self.assertEqual(
            self.task_2.user_ids,
            self.user_projectmanager,
            "The assignees set on Task 2 should be the new one and the user initially assinged should be unassigned.",
        )

        tasks.web_gantt_write({"user_ids": False})
        self.assertFalse(tasks.user_ids, "No assignees should be set on the both tasks")

        tasks.web_gantt_write({"user_ids": self.user_portal.ids})
        self.assertEqual(
            self.task_1.user_ids,
            self.user_portal,
            "User portal should be assigned to Task 1.",
        )
        self.assertEqual(
            self.task_2.user_ids,
            self.user_portal,
            "User portal should be assigned to Task 2.",
        )

        tasks.web_gantt_write({"user_ids": users.ids})
        self.assertEqual(
            self.task_1.user_ids,
            users,
            "Project user and Prohect manager should be assigned to the task 1 and portal user should be assigned.",
        )
        self.assertEqual(
            self.task_2.user_ids,
            users,
            "Project user and Prohect maanger should be assigned to the task 2 and portal user should be assigned.",
        )

    def test_project_web_gantt_write(self):
        self.project_goats.write(
            {
                "user_id": self.user_projectmanager.id,
            }
        )
        self.project_pigs.write(
            {
                "user_id": self.user_projectmanager.id,
                "date_start": "2021-09-27",
                "date": "2021-09-28",
            }
        )
        self.project_goats.web_gantt_write({"user_id": False})
        self.assertEqual(
            self.project_goats.user_id,
            self.user_projectmanager,
            "Project without a schedule should retain its assignee when `user_id` is set to False",
        )

        self.project_pigs.web_gantt_write({"user_id": False})
        self.assertFalse(
            self.project_pigs.user_id,
            "Scheduled project should have its assignee removed when `user_id` is set to False.",
        )
