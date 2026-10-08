from datetime import datetime, timedelta

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import freeze_time, tagged

from .test_project_base import TestProjectCommon


class TestDependencyTypesCommon(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.project = cls.env["project.project"].create(
            {"name": "Typed", "allow_dependencies": True}
        )
        cls.step = cls.env["project.workflow.step"].create(
            {"name": "S", "project_ids": [Command.link(cls.project.id)]}
        )

    def _task(self, name, **vals):
        return self.env["project.task"].create(
            {"name": name, "project_id": self.project.id, "step_id": self.step.id}
            | vals
        )

    def _link(self, successor, predecessor, dependency_type="fs", lag_hours=0.0):
        return self.env["project.task.dependency"].create(
            {
                "task_id": successor.id,
                "depends_on_id": predecessor.id,
                "dependency_type": dependency_type,
                "lag_hours": lag_hours,
            }
        )


@tagged("post_install", "-at_install")
class TestDependencyOneStore(TestDependencyTypesCommon):
    def test_the_m2m_reads_the_dependency_table(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self.env.flush_all()
        self.env.cr.execute(
            "INSERT INTO project_task_dependency (task_id, depends_on_id, dependency_type, lag_hours) "
            "VALUES (%s, %s, 'ss', 2.0)",
            (successor.id, predecessor.id),
        )
        self.env.invalidate_all()
        self.assertEqual(successor.predecessor_ids, predecessor)
        self.assertEqual(predecessor.successor_ids, successor)

    def test_an_m2m_link_is_one_fs_row_without_lag(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        successor.predecessor_ids = [Command.link(predecessor.id)]
        self.assertEqual(successor.dependency_ids.depends_on_id, predecessor)
        self.assertEqual(successor.dependency_ids.dependency_type, "fs")
        self.assertEqual(successor.dependency_ids.lag_hours, 0.0)
        self.assertEqual(predecessor.dependent_on_me_ids, successor.dependency_ids)

    def test_an_m2m_unlink_removes_the_typed_row(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        dependency = self._link(successor, predecessor, "ss", 4.0)
        self.assertEqual(successor.predecessor_ids, predecessor)
        successor.predecessor_ids = [Command.unlink(predecessor.id)]
        self.assertFalse(dependency.exists())
        self.assertFalse(successor.dependency_ids)

    def test_a_remapped_row_moves_the_m2m_link(self) -> None:
        a, b, c = self._task("A"), self._task("B"), self._task("C")
        dependency = self._link(c, a)
        self.assertEqual(c.predecessor_ids, a)
        dependency.depends_on_id = b
        self.assertEqual(c.predecessor_ids, b)
        self.assertFalse(a.successor_ids)
        self.assertEqual(b.successor_ids, c)

    def test_one_cycle_check_on_both_paths(self) -> None:
        a, b = self._task("A"), self._task("B")
        self._link(b, a)
        with self.assertRaises(ValidationError) as via_row:
            self._link(a, b)
        with self.assertRaises(ValidationError) as via_m2m:
            a.predecessor_ids = [Command.link(b.id)]
        self.assertEqual(str(via_row.exception), str(via_m2m.exception))


@tagged("post_install", "-at_install")
class TestDependencyTypeBlocking(TestDependencyTypesCommon):
    def test_finish_to_start_blocks_until_the_predecessor_closes(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "fs")
        self.assertEqual(successor.state, "blocked")
        predecessor.state = "in_progress"
        self.assertEqual(successor.state, "blocked")
        predecessor.state = "done"
        self.assertNotEqual(successor.state, "blocked")

    def test_start_to_start_blocks_until_the_predecessor_starts(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "ss")
        self.assertTrue(successor.is_blocked_by_predecessors())
        self.assertEqual(successor.state, "blocked")
        predecessor.state = "in_progress"
        self.assertFalse(successor.is_blocked_by_predecessors())
        self.assertEqual(successor.state, "in_progress")

    def test_finish_to_finish_never_blocks_the_start(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "ff")
        self.assertFalse(successor.is_blocked_by_predecessors())
        self.assertEqual(successor.state, "todo")
        successor.state = "in_progress"
        self.assertEqual(successor.state, "in_progress")

    def test_finish_to_finish_refuses_closing_before_the_predecessor(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "ff")
        with self.assertRaises(ValidationError):
            successor.state = "done"
        predecessor.state = "done"
        successor.state = "done"
        self.assertEqual(successor.state, "done")

    def test_start_to_finish_refuses_closing_before_the_predecessor_starts(
        self,
    ) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "sf")
        self.assertEqual(successor.state, "todo")
        with self.assertRaises(ValidationError):
            successor.state = "done"
        predecessor.state = "in_progress"
        successor.state = "done"
        self.assertEqual(successor.state, "done")

    def test_cancelling_is_not_finishing(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "ff")
        successor.state = "canceled"
        self.assertEqual(successor.state, "canceled")

    def test_changing_the_type_reblocks(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        dependency = self._link(successor, predecessor, "ff")
        self.assertEqual(successor.state, "todo")
        dependency.dependency_type = "fs"
        self.assertEqual(successor.state, "blocked")
        dependency.dependency_type = "ss"
        self.assertEqual(successor.state, "blocked")
        predecessor.state = "in_progress"
        self.assertEqual(successor.state, "in_progress")

    def test_an_archived_predecessor_does_not_block(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "ss")
        predecessor.active = False
        self.assertFalse(successor.is_blocked_by_predecessors())


@tagged("post_install", "-at_install")
class TestDependencyTypeDates(TestDependencyTypesCommon):
    day = datetime(2100, 3, 1)

    def _at(self, hour):
        return self.day + timedelta(hours=hour)

    def _warned(self, task):
        found = self.env["project.task"].search(
            [("dependency_warning", "=", True), ("id", "=", task.id)]
        )
        self.assertEqual(
            bool(task.dependency_warning), bool(found), "search agrees with compute"
        )
        return bool(task.dependency_warning)

    def test_finish_to_start_lag_delays_the_start(self) -> None:
        predecessor = self._task("P", date_start=self._at(8), date_end=self._at(10))
        successor = self._task("S", date_start=self._at(11), date_end=self._at(12))
        dependency = self._link(successor, predecessor, "fs")
        self.assertFalse(self._warned(successor))
        dependency.lag_hours = 2.0
        self.assertTrue(self._warned(successor))
        dependency.lag_hours = -2.0
        successor.date_start = self._at(9)
        self.assertFalse(self._warned(successor))

    def test_start_to_start_reads_the_predecessor_start(self) -> None:
        predecessor = self._task("P", date_start=self._at(8), date_end=self._at(12))
        successor = self._task("S", date_start=self._at(10), date_end=self._at(14))
        self._link(successor, predecessor, "ss")
        self.assertFalse(self._warned(successor))
        successor.date_start = self._at(7)
        self.assertTrue(self._warned(successor))

    def test_finish_to_finish_reads_the_ends(self) -> None:
        predecessor = self._task("P", date_start=self._at(8), date_end=self._at(12))
        successor = self._task("S", date_start=self._at(6), date_end=self._at(13))
        self._link(successor, predecessor, "ff", 2.0)
        self.assertTrue(self._warned(successor))
        successor.date_end = self._at(14)
        self.assertFalse(self._warned(successor))

    def test_start_to_finish_reads_the_predecessor_start(self) -> None:
        predecessor = self._task("P", date_start=self._at(8), date_end=self._at(20))
        successor = self._task("S", date_start=self._at(6), date_end=self._at(9))
        self._link(successor, predecessor, "sf")
        self.assertFalse(self._warned(successor))
        successor.date_end = self._at(7)
        self.assertTrue(self._warned(successor))

    def test_the_bounds_per_task_follow_type_and_lag(self) -> None:
        a = self._task("A", date_start=self._at(8), date_end=self._at(10))
        b = self._task("B", date_start=self._at(9), date_end=self._at(12))
        s = self._task("S")
        self._link(s, a, "fs", 1.0)
        self._link(s, b, "ss", 1.0)
        t = self._task("T")
        self._link(t, a, "ff", 3.0)
        self._link(t, b, "sf")
        bounds = (s | t)._get_dependency_bounds_per_task()
        self.assertEqual(bounds[s.id], {"date_start": self._at(11)})
        self.assertEqual(bounds[t.id], {"date_end": self._at(13)})

    @freeze_time("2100-02-25")
    def test_scheduling_honours_finish_to_start_lag(self) -> None:
        predecessor = self._task(
            "P",
            date_start=datetime(2100, 3, 1, 7),
            date_end=datetime(2100, 3, 1, 16),
        )
        successor = self._task(
            "S", planned_hours=2.0, user_ids=[Command.set(self.user_projectmanager.ids)]
        )
        self._link(successor, predecessor, "fs", 24.0)
        successor._schedule_tasks(
            {
                "date_start": "2100-03-01 00:00:00",
                "user_ids": self.user_projectmanager.ids,
            },
            datetime(2100, 3, 31),
        )
        self.assertGreaterEqual(successor.date_start, datetime(2100, 3, 2, 16))

    @freeze_time("2100-02-25")
    def test_scheduling_holds_a_finish_to_finish_end(self) -> None:
        predecessor = self._task(
            "P",
            date_start=datetime(2100, 3, 1, 7),
            date_end=datetime(2100, 3, 3, 16),
        )
        successor = self._task(
            "S", planned_hours=2.0, user_ids=[Command.set(self.user_projectmanager.ids)]
        )
        self._link(successor, predecessor, "ff")
        successor._schedule_tasks(
            {
                "date_start": "2100-03-01 00:00:00",
                "user_ids": self.user_projectmanager.ids,
            },
            datetime(2100, 3, 31),
        )
        self.assertLess(successor.date_start, datetime(2100, 3, 2))
        self.assertGreaterEqual(successor.date_end, datetime(2100, 3, 3, 16))

    def test_copy_keeps_type_and_lag(self) -> None:
        a, b = self._task("A"), self._task("B")
        self._link(b, a, "sf", 6.0)
        copied = self.project.copy()
        rows = self.env["project.task.dependency"].search(
            [("project_id", "=", copied.id)]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows.dependency_type, rows.lag_hours), ("sf", 6.0))
        self.assertEqual(rows.task_id.predecessor_ids, rows.depends_on_id)
