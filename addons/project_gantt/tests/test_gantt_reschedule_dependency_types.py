from datetime import datetime

from odoo.tests.common import freeze_time, tagged

from .gantt_reschedule_dates_common import ProjectGanttRescheduleCommon, fake_now


@tagged("gantt_reschedule", "post_install", "-at_install")
@freeze_time(fake_now)
class TestGanttRescheduleDependencyTypes(ProjectGanttRescheduleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.typed_project = cls.env["project.project"].create(
            {"name": "Typed dependencies", "allow_dependencies": True}
        )

    def _create_task(self, name, user, start, end):
        return self.ProjectTask.create(
            {
                "name": name,
                "project_id": self.typed_project.id,
                "user_ids": user.ids,
                "date_start": start,
                "date_end": end,
            }
        )

    def _link(self, predecessor, successor, dependency_type, lag_hours=0.0):
        self.env["project.task.dependency"].create(
            {
                "task_id": successor.id,
                "depends_on_id": predecessor.id,
                "dependency_type": dependency_type,
                "lag_hours": lag_hours,
            }
        )

    @staticmethod
    def _vals(start, end):
        return {
            "date_start": start.strftime("%Y-%m-%d %H:%M:%S"),
            "date_end": end.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _forward(self, dependency_type, lag_hours=0.0):
        predecessor = self._create_task(
            "P", self.user1, datetime(2021, 6, 7, 8), datetime(2021, 6, 7, 10)
        )
        successor = self._create_task(
            "S", self.user2, datetime(2021, 6, 8, 8), datetime(2021, 6, 8, 11)
        )
        self._link(predecessor, successor, dependency_type, lag_hours)
        res = self.gantt_reschedule_consume_buffer(
            predecessor,
            self._vals(datetime(2021, 6, 8, 13), datetime(2021, 6, 8, 15)),
        )
        self.assertEqual(res["type"], "success", res["message"])
        return predecessor, successor

    def _backward(self, dependency_type, lag_hours=0.0):
        predecessor = self._create_task(
            "P", self.user1, datetime(2021, 6, 7, 13), datetime(2021, 6, 7, 16)
        )
        successor = self._create_task(
            "S", self.user2, datetime(2021, 6, 9, 8), datetime(2021, 6, 9, 10)
        )
        self._link(predecessor, successor, dependency_type, lag_hours)
        res = self.gantt_reschedule_consume_buffer(
            successor,
            self._vals(datetime(2021, 6, 7, 9), datetime(2021, 6, 7, 11)),
        )
        self.assertEqual(res["type"], "success", res["message"])
        return predecessor, successor

    def test_forward_finish_to_start(self):
        _predecessor, successor = self._forward("fs")
        self.assert_new_dates(
            successor, datetime(2021, 6, 8, 15), datetime(2021, 6, 9, 9)
        )

    def test_forward_start_to_start(self):
        _predecessor, successor = self._forward("ss")
        self.assert_new_dates(
            successor,
            datetime(2021, 6, 8, 13),
            datetime(2021, 6, 8, 16),
            "the successor starts with the predecessor's new start",
        )

    def test_forward_finish_to_finish(self):
        _predecessor, successor = self._forward("ff")
        self.assert_new_dates(
            successor,
            datetime(2021, 6, 8, 11),
            datetime(2021, 6, 8, 15),
            "the successor ends with the predecessor, its 3 hours around lunch",
        )

    def test_forward_start_to_finish(self):
        _predecessor, successor = self._forward("sf")
        self.assert_new_dates(
            successor,
            datetime(2021, 6, 8, 9),
            datetime(2021, 6, 8, 13),
            "the successor ends when the predecessor starts; the lunch hour "
            "before it is no working time",
        )

    def test_forward_finish_to_start_with_lag(self):
        _predecessor, successor = self._forward("fs", lag_hours=2)
        self.assert_new_dates(
            successor,
            datetime(2021, 6, 9, 8),
            datetime(2021, 6, 9, 11),
            "15h + 2 calendar hours is 17h: the next working hour is Wednesday 8h",
        )

    def test_forward_finish_to_finish_with_lead(self):
        _predecessor, successor = self._forward("ff", lag_hours=-1)
        self.assert_new_dates(
            successor, datetime(2021, 6, 8, 10), datetime(2021, 6, 8, 14)
        )

    def test_forward_start_to_start_not_violated_is_not_moved(self):
        predecessor = self._create_task(
            "P", self.user1, datetime(2021, 6, 7, 8), datetime(2021, 6, 7, 10)
        )
        successor = self._create_task(
            "S", self.user2, datetime(2021, 6, 8, 10), datetime(2021, 6, 8, 11)
        )
        self._link(predecessor, successor, "ss")
        self.gantt_reschedule_consume_buffer(
            predecessor,
            self._vals(datetime(2021, 6, 8, 9), datetime(2021, 6, 8, 12)),
        )
        self.assert_new_dates(
            successor,
            datetime(2021, 6, 8, 10),
            datetime(2021, 6, 8, 11),
            "starting inside the predecessor is what start-to-start allows",
        )

    def test_forward_start_to_start_maintain_buffer(self):
        predecessor = self._create_task(
            "P", self.user1, datetime(2021, 6, 7, 8), datetime(2021, 6, 7, 10)
        )
        successor = self._create_task(
            "S", self.user2, datetime(2021, 6, 7, 9), datetime(2021, 6, 7, 11)
        )
        self._link(predecessor, successor, "ss")
        self.gantt_reschedule_maintain_buffer(
            predecessor,
            self._vals(datetime(2021, 6, 8, 13), datetime(2021, 6, 8, 15)),
        )
        self.assert_new_dates(
            successor,
            datetime(2021, 6, 8, 14),
            datetime(2021, 6, 8, 16),
            "the hour between both starts is kept",
        )

    def test_forward_finish_to_finish_maintain_buffer(self):
        predecessor = self._create_task(
            "P", self.user1, datetime(2021, 6, 7, 8), datetime(2021, 6, 7, 10)
        )
        successor = self._create_task(
            "S", self.user2, datetime(2021, 6, 7, 9), datetime(2021, 6, 7, 12)
        )
        self._link(predecessor, successor, "ff")
        self.gantt_reschedule_maintain_buffer(
            predecessor,
            self._vals(datetime(2021, 6, 8, 13), datetime(2021, 6, 8, 15)),
        )
        self.assert_new_dates(
            successor,
            datetime(2021, 6, 8, 14),
            datetime(2021, 6, 8, 17),
            "the 2 hours between both ends are kept, though the successor "
            "started before the predecessor ended",
        )

    def test_forward_mixed_chain(self):
        predecessor = self._create_task(
            "P", self.user1, datetime(2021, 6, 7, 8), datetime(2021, 6, 7, 10)
        )
        middle = self._create_task(
            "M", self.user2, datetime(2021, 6, 7, 9), datetime(2021, 6, 7, 11)
        )
        last = self._create_task(
            "L", self.user1, datetime(2021, 6, 7, 10), datetime(2021, 6, 7, 11)
        )
        self._link(predecessor, middle, "ss")
        self._link(middle, last, "ff")
        self.gantt_reschedule_consume_buffer(
            predecessor,
            self._vals(datetime(2021, 6, 8, 8), datetime(2021, 6, 8, 10)),
        )
        self.assert_new_dates(middle, datetime(2021, 6, 8, 8), datetime(2021, 6, 8, 10))
        self.assert_new_dates(
            last,
            datetime(2021, 6, 8, 10),
            datetime(2021, 6, 8, 11),
            "the last task ends no earlier than the middle one, after the "
            "predecessor it shares an assignee with",
        )

    def test_backward_finish_to_start(self):
        predecessor, _successor = self._backward("fs")
        self.assert_new_dates(
            predecessor, datetime(2021, 6, 4, 15), datetime(2021, 6, 7, 9)
        )

    def test_backward_start_to_start(self):
        predecessor, _successor = self._backward("ss")
        self.assert_new_dates(
            predecessor,
            datetime(2021, 6, 7, 9),
            datetime(2021, 6, 7, 12),
            "the predecessor starts no later than the successor's new start",
        )

    def test_backward_finish_to_finish(self):
        predecessor, _successor = self._backward("ff")
        self.assert_new_dates(
            predecessor, datetime(2021, 6, 7, 8), datetime(2021, 6, 7, 11)
        )

    def test_backward_start_to_finish(self):
        predecessor, _successor = self._backward("sf")
        self.assert_new_dates(
            predecessor,
            datetime(2021, 6, 7, 11),
            datetime(2021, 6, 7, 15),
            "the predecessor starts no later than the successor's new end",
        )

    def test_backward_finish_to_start_with_lead(self):
        predecessor, _successor = self._backward("fs", lag_hours=-1)
        self.assert_new_dates(
            predecessor, datetime(2021, 6, 4, 16), datetime(2021, 6, 7, 10)
        )

    def test_backward_start_to_finish_maintain_buffer(self):
        predecessor = self._create_task(
            "P", self.user1, datetime(2021, 6, 7, 13), datetime(2021, 6, 7, 16)
        )
        successor = self._create_task(
            "S", self.user2, datetime(2021, 6, 7, 14), datetime(2021, 6, 7, 16)
        )
        self._link(predecessor, successor, "sf")
        self.gantt_reschedule_maintain_buffer(
            successor,
            self._vals(datetime(2021, 6, 7, 9), datetime(2021, 6, 7, 11)),
        )
        self.assert_new_dates(
            predecessor,
            datetime(2021, 6, 7, 8),
            datetime(2021, 6, 7, 11),
            "the 3 hours from the predecessor's start to the successor's end "
            "are kept, though the successor started before the predecessor ended",
        )

    def test_backward_finish_to_finish_not_violated_is_not_moved(self):
        predecessor = self._create_task(
            "P", self.user1, datetime(2021, 6, 7, 8), datetime(2021, 6, 7, 16)
        )
        successor = self._create_task(
            "S", self.user2, datetime(2021, 6, 9, 8), datetime(2021, 6, 9, 10)
        )
        self._link(predecessor, successor, "ff")
        self.gantt_reschedule_consume_buffer(
            successor,
            self._vals(datetime(2021, 6, 7, 15), datetime(2021, 6, 7, 17)),
        )
        self.assert_new_dates(
            predecessor,
            datetime(2021, 6, 7, 8),
            datetime(2021, 6, 7, 16),
            "a successor may start before its finish-to-finish predecessor ends",
        )

    def test_backward_start_to_start_reaches_the_bound_across_lunch(self):
        predecessor = self._create_task(
            "P", self.user1, datetime(2021, 6, 7, 13), datetime(2021, 6, 7, 16)
        )
        successor = self._create_task(
            "S", self.user2, datetime(2021, 6, 9, 8), datetime(2021, 6, 9, 10)
        )
        self._link(predecessor, successor, "ss")
        self.gantt_reschedule_consume_buffer(
            successor,
            self._vals(datetime(2021, 6, 7, 12, 30), datetime(2021, 6, 7, 14, 30)),
        )
        self.assert_new_dates(
            predecessor,
            datetime(2021, 6, 7, 12, 30),
            datetime(2021, 6, 7, 16),
            "the work still starts at 13h; only the lunch break lies before it",
        )

    def test_backward_start_to_start_does_not_reach_across_booked_time(self):
        predecessor = self._create_task(
            "P", self.user1, datetime(2021, 6, 7, 13), datetime(2021, 6, 7, 16)
        )
        successor = self._create_task(
            "S", self.user2, datetime(2021, 6, 9, 8), datetime(2021, 6, 9, 10)
        )
        self._create_task(
            "Booked", self.user1, datetime(2021, 6, 7, 8), datetime(2021, 6, 7, 10)
        )
        self._link(predecessor, successor, "ss")
        self.gantt_reschedule_consume_buffer(
            successor,
            self._vals(datetime(2021, 6, 7, 9), datetime(2021, 6, 7, 11)),
        )
        self.assert_new_dates(
            predecessor,
            datetime(2021, 6, 4, 14),
            datetime(2021, 6, 4, 17),
            "Monday 9h-10h is booked, so the predecessor ends before 9h instead",
        )

    def _forward_through_a_task_left_in_place(self, dependency_type):
        moved = self._create_task(
            "A", self.user1, datetime(2021, 6, 7, 8), datetime(2021, 6, 7, 10)
        )
        kept = self._create_task(
            "B", self.user2, datetime(2021, 6, 8, 8), datetime(2021, 6, 8, 10)
        )
        bounded = self._create_task(
            "C", self.user1, datetime(2021, 6, 9, 8), datetime(2021, 6, 9, 10)
        )
        overlapped = self._create_task(
            "D", self.user2, datetime(2021, 6, 9, 9), datetime(2021, 6, 9, 11)
        )
        self._link(moved, kept, "fs")
        self._link(kept, bounded, dependency_type)
        self._link(bounded, overlapped, "fs")
        res = self.gantt_reschedule_consume_buffer(
            moved, self._vals(datetime(2021, 6, 7, 13), datetime(2021, 6, 7, 15))
        )
        self.assertEqual(res["type"], "success", res["message"])
        self.assert_new_dates(kept, datetime(2021, 6, 8, 8), datetime(2021, 6, 8, 10))
        self.assertFalse(
            bounded._web_gantt_is_candidate_in_conflict(
                "date_start", "date_end", "predecessor_ids", "successor_ids"
            ),
            "every link around the task placed again holds",
        )
        return bounded

    def test_forward_finish_to_start_through_a_task_left_in_place(self):
        bounded = self._forward_through_a_task_left_in_place("fs")
        self.assert_new_dates(
            bounded,
            datetime(2021, 6, 8, 10),
            datetime(2021, 6, 8, 12),
            "the task starts when the task left in place ends",
        )

    def test_forward_start_to_start_through_a_task_left_in_place(self):
        bounded = self._forward_through_a_task_left_in_place("ss")
        self.assert_new_dates(
            bounded,
            datetime(2021, 6, 8, 8),
            datetime(2021, 6, 8, 10),
            "the task starts with the task left in place",
        )

    def test_forward_finish_to_finish_through_a_task_left_in_place(self):
        bounded = self._forward_through_a_task_left_in_place("ff")
        self.assert_new_dates(
            bounded,
            datetime(2021, 6, 9, 8),
            datetime(2021, 6, 9, 10),
            "ending with the task left in place would start it before its "
            "own start, so it stays",
        )

    def test_forward_start_to_finish_through_a_task_left_in_place(self):
        bounded = self._forward_through_a_task_left_in_place("sf")
        self.assert_new_dates(
            bounded, datetime(2021, 6, 9, 8), datetime(2021, 6, 9, 10)
        )

    def _backward_through_a_task_left_in_place(self, dependency_type):
        overlapped = self._create_task(
            "W", self.user2, datetime(2021, 6, 9, 14), datetime(2021, 6, 9, 16)
        )
        bounded = self._create_task(
            "X", self.user1, datetime(2021, 6, 9, 15), datetime(2021, 6, 9, 17)
        )
        kept = self._create_task(
            "Y", self.user2, datetime(2021, 6, 10, 15), datetime(2021, 6, 10, 17)
        )
        moved = self._create_task(
            "Z", self.user1, datetime(2021, 6, 11, 15), datetime(2021, 6, 11, 17)
        )
        self._link(overlapped, bounded, "fs")
        self._link(bounded, kept, dependency_type)
        self._link(kept, moved, "fs")
        res = self.gantt_reschedule_consume_buffer(
            moved, self._vals(datetime(2021, 6, 11, 10), datetime(2021, 6, 11, 12))
        )
        self.assertEqual(res["type"], "success", res["message"])
        self.assert_new_dates(
            kept, datetime(2021, 6, 10, 15), datetime(2021, 6, 10, 17)
        )
        self.assertFalse(
            bounded._web_gantt_is_candidate_in_conflict(
                "date_start", "date_end", "predecessor_ids", "successor_ids"
            ),
            "every link around the task placed again holds",
        )
        return bounded

    def test_backward_finish_to_start_through_a_task_left_in_place(self):
        bounded = self._backward_through_a_task_left_in_place("fs")
        self.assert_new_dates(
            bounded,
            datetime(2021, 6, 10, 13),
            datetime(2021, 6, 10, 15),
            "the task ends when the task left in place starts",
        )

    def test_backward_finish_to_finish_through_a_task_left_in_place(self):
        bounded = self._backward_through_a_task_left_in_place("ff")
        self.assert_new_dates(
            bounded,
            datetime(2021, 6, 10, 15),
            datetime(2021, 6, 10, 17),
            "the task ends with the task left in place",
        )

    def test_backward_start_to_start_through_a_task_left_in_place(self):
        bounded = self._backward_through_a_task_left_in_place("ss")
        self.assert_new_dates(
            bounded,
            datetime(2021, 6, 9, 15),
            datetime(2021, 6, 9, 17),
            "starting with the task left in place would end it after its own "
            "end, so it stays",
        )

    def test_backward_start_to_finish_through_a_task_left_in_place(self):
        bounded = self._backward_through_a_task_left_in_place("sf")
        self.assert_new_dates(
            bounded, datetime(2021, 6, 9, 15), datetime(2021, 6, 9, 17)
        )

    def test_gantt_dependency_types(self):
        predecessor = self._create_task(
            "P", self.user1, datetime(2021, 6, 7, 8), datetime(2021, 6, 7, 10)
        )
        successor = self._create_task(
            "S", self.user2, datetime(2021, 6, 8, 8), datetime(2021, 6, 8, 11)
        )
        self._link(predecessor, successor, "sf", lag_hours=1.5)
        self.assertEqual(
            successor.gantt_dependency_types,
            {str(predecessor.id): {"type": "sf", "lag": 1.5}},
        )
        self.assertFalse(predecessor.gantt_dependency_types)
