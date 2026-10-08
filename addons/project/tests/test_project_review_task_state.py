from datetime import timedelta

from freezegun import freeze_time

from odoo import Command, fields

from .test_project_base import TestProjectCommon


class TestTaskStateFromStep(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref("project.group_project_recurring_tasks")
        cls.project = cls.env["project.project"].create(
            {
                "name": "States",
                "allow_dependencies": True,
                "allow_recurring_tasks": True,
            }
        )
        cls.step_doing, cls.step_review, cls.step_done = cls.env[
            "project.workflow.step"
        ].create(
            [
                {
                    "name": "Doing",
                    "sequence": 1,
                    "task_state": "in_progress",
                    "project_ids": [Command.link(cls.project.id)],
                },
                {
                    "name": "Review",
                    "sequence": 2,
                    "project_ids": [Command.link(cls.project.id)],
                },
                {
                    "name": "Done",
                    "sequence": 3,
                    "task_state": "done",
                    "project_ids": [Command.link(cls.project.id)],
                },
            ]
        )

    def _task(self, **vals):
        return self.env["project.task"].create(
            {"name": "t", "project_id": self.project.id, **vals}
        )

    def test_a_new_task_takes_its_steps_state(self) -> None:
        self.assertEqual(self._task(step_id=self.step_doing.id).state, "in_progress")

    def test_moving_into_a_step_applies_its_state(self) -> None:
        task = self._task(step_id=self.step_review.id)
        self.assertEqual(task.state, "todo")
        task.step_id = self.step_doing
        self.assertEqual(task.state, "in_progress")

    def test_a_predecessor_change_keeps_a_state_set_by_hand(self) -> None:
        predecessor = self._task(step_id=self.step_review.id)
        task = self._task(
            step_id=self.step_doing.id,
            predecessor_ids=[Command.link(predecessor.id)],
        )
        self.assertEqual(task.state, "blocked")
        task.state = "done"
        predecessor.state = "done"
        self.assertEqual(task.state, "done")

    def test_unblocking_does_not_reapply_the_steps_state(self) -> None:
        predecessor = self._task(step_id=self.step_review.id)
        task = self._task(step_id=self.step_review.id)
        task.state = "approved"
        task.predecessor_ids = predecessor
        self.assertEqual(task.state, "blocked")
        predecessor.state = "done"
        self.assertEqual(task.state, "in_progress")

    def test_rewriting_the_same_step_keeps_an_approval(self) -> None:
        task = self._task(step_id=self.step_review.id)
        task.state = "approved"
        task.write({"step_id": self.step_review.id})
        self.assertEqual(task.state, "approved")

    def test_moving_a_recurring_task_into_a_done_step_creates_the_next_one(
        self,
    ) -> None:
        task = self._task(
            step_id=self.step_doing.id,
            recurring_task=True,
            repeat_interval=1,
            repeat_unit="week",
            repeat_type="forever",
        )
        task.step_id = self.step_done
        self.assertEqual(task.state, "done")
        self.assertEqual(len(task.recurrence_id.task_ids), 2)

    def test_changing_a_steps_state_does_not_restate_its_tasks(self) -> None:
        task = self._task(step_id=self.step_doing.id)
        task.state = "approved"
        self.step_doing.task_state = "done"
        self.assertEqual(task.state, "approved")


class TestDependencyRowsDriveState(TestProjectCommon):
    def test_a_dependency_row_blocks_its_task(self) -> None:
        self.project_pigs.allow_dependencies = True
        predecessor, task = self.env["project.task"].create(
            [
                {"name": "a", "project_id": self.project_pigs.id},
                {"name": "b", "project_id": self.project_pigs.id},
            ]
        )
        self.env["project.task.dependency"].create(
            {"task_id": task.id, "depends_on_id": predecessor.id}
        )
        self.env.invalidate_all()
        self.assertEqual(task.predecessor_ids, predecessor)
        self.assertEqual(task.state, "blocked")


class TestRecurrenceEnds(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref("project.group_project_recurring_tasks")
        cls.project_pigs.allow_recurring_tasks = True

    def _recurring(self, **vals):
        return self.env["project.task"].create(
            {
                "name": "r",
                "project_id": self.project_pigs.id,
                "recurring_task": True,
                "repeat_interval": 1,
                "repeat_unit": "week",
                "repeat_type": "forever",
                **vals,
            }
        )

    def test_deleting_the_last_occurrence_ends_the_series_everywhere(self) -> None:
        first = self._recurring()
        first.state = "done"
        second = first.recurrence_id.task_ids - first
        self.assertTrue(second)
        second.unlink()
        self.assertFalse(first.recurrence_id)
        self.assertFalse(first.recurring_task)

    def test_an_undated_until_series_stops_after_its_end_date(self) -> None:
        until = fields.Date.today() + timedelta(days=2)
        task = self._recurring(repeat_type="until", repeat_until=until)
        self.assertFalse(task.date_end)
        with freeze_time(until + timedelta(days=3)):
            task.state = "done"
        self.assertEqual(len(task.recurrence_id.task_ids), 1)


class TestDependencyCounts(TestProjectCommon):
    def test_counts_agree_between_a_form_and_the_saved_task(self) -> None:
        self.project_pigs.allow_dependencies = True
        open_pred, closed_pred = self.env["project.task"].create(
            [
                {"name": "open", "project_id": self.project_pigs.id},
                {"name": "closed", "project_id": self.project_pigs.id, "state": "done"},
            ]
        )
        task = self.env["project.task"].create(
            {
                "name": "t",
                "project_id": self.project_pigs.id,
                "predecessor_ids": [Command.set((open_pred | closed_pred).ids)],
            }
        )
        saved = (task.predecessor_count, task.closed_predecessor_count)
        new = task.new(origin=task)
        self.assertEqual(saved, (new.predecessor_count, new.closed_predecessor_count))
        self.assertEqual(saved, (2, 1))
        self.assertEqual(open_pred.successor_count, 1)
        self.env["project.task"].create(
            {
                "name": "closed successor",
                "project_id": self.project_pigs.id,
                "state": "done",
                "predecessor_ids": [Command.link(open_pred.id)],
            }
        )
        self.env.invalidate_all()
        self.assertEqual(open_pred.successor_count, 1)
        self.assertEqual(open_pred.new(origin=open_pred).successor_count, 1)
        task.state = "done"
        self.assertEqual(open_pred.successor_count, 0)
