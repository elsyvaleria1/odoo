from datetime import datetime

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import freeze_time, new_test_user, tagged

from .test_project_base import TestProjectCommon
from .test_project_task_dependency_types import TestDependencyTypesCommon


@tagged("post_install", "-at_install")
class TestFinishRefusalIsATransition(TestDependencyTypesCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.done_step = cls.env["project.workflow.step"].create(
            {
                "name": "Finished",
                "task_state": "done",
                "project_ids": [Command.link(cls.project.id)],
            }
        )

    def test_reopening_a_finish_to_finish_predecessor_keeps_the_done_successor(
        self,
    ) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "ff")
        predecessor.state = "done"
        successor.state = "done"
        predecessor.state = "in_progress"
        self.env.flush_all()
        self.assertEqual(successor.state, "done")
        self.assertEqual(predecessor.state, "in_progress")

    def test_a_start_to_finish_predecessor_back_to_todo_keeps_the_done_successor(
        self,
    ) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "sf")
        predecessor.state = "in_progress"
        successor.state = "done"
        predecessor.state = "todo"
        self.env.flush_all()
        self.assertEqual(successor.state, "done")

    def test_linking_an_open_predecessor_to_a_done_task_is_no_transition(
        self,
    ) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        successor.state = "done"
        self._link(successor, predecessor, "ff")
        self.env.flush_all()
        self.assertEqual(successor.state, "done")

    def test_a_done_task_written_done_again_is_no_transition(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        successor.state = "done"
        self._link(successor, predecessor, "ff")
        successor.write({"state": "done", "name": "S again"})
        self.assertEqual(successor.state, "done")

    def test_dragging_into_a_done_step_is_still_refused(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "ff")
        with self.assertRaises(ValidationError):
            successor.write({"step_id": self.done_step.id})
        predecessor.state = "done"
        successor.write({"step_id": self.done_step.id})
        self.assertEqual(successor.state, "done")

    def test_a_waiting_task_dragged_into_a_done_step_is_done(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "fs")
        self.assertEqual(successor.state, "blocked")
        successor.write({"step_id": self.done_step.id})
        self.assertEqual(successor.state, "done")

    def test_a_waiting_task_with_an_open_finish_predecessor_is_still_refused(
        self,
    ) -> None:
        start, finish = self._task("Start"), self._task("Finish")
        successor = self._task("S")
        self._link(successor, start, "fs")
        self._link(successor, finish, "ff")
        self.assertEqual(successor.state, "blocked")
        with self.assertRaises(ValidationError):
            successor.write({"step_id": self.done_step.id})

    def test_closing_a_recurrence_occurrence_is_still_refused(self) -> None:
        predecessor = self._task("P")
        recurring = self._task(
            "R",
            recurring_task=True,
            repeat_interval=1,
            repeat_unit="week",
            repeat_type="forever",
        )
        self._link(recurring, predecessor, "ff")
        with self.assertRaises(ValidationError):
            recurring.state = "done"
        self.assertEqual(recurring.recurrence_id.task_ids, recurring)

    def test_creating_a_done_task_with_an_open_finish_predecessor_is_refused(
        self,
    ) -> None:
        predecessor = self._task("P")
        with self.assertRaises(ValidationError):
            self._task(
                "S",
                state="done",
                dependency_ids=[
                    Command.create(
                        {"depends_on_id": predecessor.id, "dependency_type": "ff"}
                    )
                ],
            )

    def test_a_batch_with_one_refused_task_is_refused_whole(self) -> None:
        predecessor = self._task("P")
        tasks = self._task("M1") | self._task("M2")
        self._link(tasks[0], predecessor, "ff")
        with self.assertRaises(ValidationError):
            tasks.write({"state": "done"})


@tagged("post_install", "-at_install")
class TestFinishRefusalNamesOnlyReadableTasks(TestDependencyTypesCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        (cls.project_pigs | cls.project_goats).allow_dependencies = True
        cls.hidden = cls.env["project.task"].create(
            {"name": "Hidden Goat Plan", "project_id": cls.project_goats.id}
        )

    def test_a_project_user_reads_no_hidden_predecessor_name(self) -> None:
        successor = self.task_1
        visible = self.task_2
        self._link(successor, self.hidden, "ff")
        self._link(successor, visible, "ff")
        with self.assertRaises(ValidationError) as refused:
            successor.with_user(self.user_projectuser).write({"state": "done"})
        message = str(refused.exception)
        self.assertNotIn(self.hidden.name, message)
        self.assertIn(visible.name, message)
        self.assertIn("1 other task", message)

    def test_a_portal_collaborator_reads_no_hidden_predecessor_name(self) -> None:
        portal_user = self.user_portal
        project = self.env["project.project"].create(
            {
                "name": "Shared",
                "privacy_visibility": "portal",
                "allow_dependencies": True,
            }
        )
        successor = self.env["project.task"].create(
            {"name": "Shared Task", "project_id": project.id}
        )
        self.env["wizard.project.project.share"].create(
            {
                "res_model": "project.project",
                "res_id": project.id,
                "collaborator_ids": [
                    Command.create(
                        {"partner_id": portal_user.partner_id.id, "access_mode": "edit"}
                    ),
                ],
            }
        ).action_send_mail()
        self._link(successor, self.hidden, "ff")
        self.env.invalidate_all()
        with self.assertRaises(ValidationError) as refused:
            successor.with_user(portal_user).write({"state": "done"})
        message = str(refused.exception)
        self.assertNotIn(self.hidden.name, message)
        self.assertIn("1 other task", message)


@tagged("post_install", "-at_install")
class TestSelfDependency(TestDependencyTypesCommon):
    def test_a_self_link_through_predecessors_is_a_validation_error(self) -> None:
        task = self._task("T")
        with self.assertRaises(ValidationError):
            task.predecessor_ids = [Command.link(task.id)]
        with self.assertRaises(ValidationError):
            task.write({"predecessor_ids": [Command.set([task.id])]})

    def test_a_self_link_through_successors_is_a_validation_error(self) -> None:
        task = self._task("T")
        with self.assertRaises(ValidationError):
            task.successor_ids = [Command.link(task.id)]


@tagged("post_install", "-at_install")
class TestCopiedDependencies(TestDependencyTypesCommon):
    def _links(self, project):
        rows = (
            self.env["project.task.dependency"]
            .with_context(active_test=False)
            .search(
                [
                    "|",
                    ("task_id.project_id", "=", project.id),
                    ("depends_on_id.project_id", "=", project.id),
                ]
            )
        )
        return sorted(
            (
                row.task_id.name,
                row.task_id.project_id.name,
                row.depends_on_id.name,
                row.depends_on_id.project_id.name,
                row.dependency_type,
                row.lag_hours,
            )
            for row in rows
        )

    def test_a_project_user_copies_a_task_linked_to_an_unreadable_one(self) -> None:
        (self.project_pigs | self.project_goats).allow_dependencies = True
        hidden = self.env["project.task"].create(
            {"name": "Hidden", "project_id": self.project_goats.id}
        )
        successor, visible = self.task_1, self.task_2
        self.assertFalse(hidden.with_user(self.user_projectuser).has_access("read"))
        self._link(successor, hidden, "ss", 2.0)
        self._link(successor, visible, "ff", 3.0)
        copied = successor.with_user(self.user_projectuser).copy()
        rows = copied.sudo().dependency_ids
        self.assertEqual(rows.depends_on_id, visible)
        self.assertEqual((rows.dependency_type, rows.lag_hours), ("ff", 3.0))

    def test_a_project_copy_keeps_the_links_of_an_archived_task(self) -> None:
        a, b, c, e = self._task("A"), self._task("B"), self._task("C"), self._task("E")
        self._link(a, b, "ss", 2.0)
        self._link(c, a, "ff", 1.0)
        self._link(e, c, "fs", 0.0)
        c.action_archive()
        copied = self.project.copy({"name": "Copied"})
        self.assertEqual(
            self._links(copied),
            [
                ("A", "Copied", "B", "Copied", "ss", 2.0),
                ("C", "Copied", "A", "Copied", "ff", 1.0),
                ("E", "Copied", "C", "Copied", "fs", 0.0),
            ],
        )

    def test_a_copy_drops_a_link_to_an_archived_task_left_behind(self) -> None:
        a, z = self._task("A"), self._task("Z")
        self._link(a, z, "ff", 1.0)
        z.action_archive()
        copied = a.copy()
        self.assertFalse(copied.dependency_ids)

    def test_a_copied_archived_task_keeps_its_active_neighbours(self) -> None:
        a, c, e = self._task("A"), self._task("C"), self._task("E")
        self._link(c, a, "ff", 1.0)
        self._link(e, c, "sf", -2.0)
        c.action_archive()
        copied = c.copy()
        self.assertEqual(
            [
                (r.depends_on_id, r.dependency_type, r.lag_hours)
                for r in copied.dependency_ids
            ],
            [(a, "ff", 1.0)],
        )
        self.assertEqual(
            [
                (r.task_id, r.dependency_type, r.lag_hours)
                for r in copied.dependent_on_me_ids
            ],
            [(e, "sf", -2.0)],
        )


@tagged("post_install", "-at_install")
class TestFirstAssignmentFallback(TestDependencyTypesCommon):
    def test_a_late_assignment_date_falls_back_to_now(self) -> None:
        task = self._task("T")
        task.user_ids = self.user_projectuser
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE project_task SET create_date = '2026-01-01 08:00:00', "
            "date_assign = NULL, date_first_assign = NULL WHERE id = %s",
            (task.id,),
        )
        task.invalidate_recordset()
        self.env.add_to_compute(task._fields["date_first_assign"], task)
        self.env.flush_all()
        self.assertEqual(task.date_first_assign, self.env.cr.now())

    def test_an_assignment_at_create_reads_the_creation(self) -> None:
        with freeze_time("2026-01-01 08:00:00"):
            task = self._task("T", user_ids=self.user_projectuser.ids)
            self.env.flush_all()
        self.assertEqual(task.date_first_assign, datetime(2026, 1, 1, 8))


@tagged("post_install", "-at_install")
class TestLagIsPlanningOnly(TestDependencyTypesCommon):
    def test_start_to_start_lag_does_not_hold_the_start(self) -> None:
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, "ss", 5.0)
        self.assertEqual(successor.state, "blocked")
        predecessor.state = "in_progress"
        self.assertEqual(successor.state, "in_progress")
        lag_help = self.env["project.task.dependency"]._fields["lag_hours"].help
        self.assertIn("not the waiting state", lag_help)


@tagged("post_install", "-at_install")
class TestPrivateTaskCreateKeepsGivenAssignees(TestProjectCommon):
    def test_a_private_task_adds_its_creator_to_the_given_users(self) -> None:
        other = new_test_user(
            self.env,
            login="k_private_other",
            groups="base.group_user,project.group_project_user",
        )
        task = (
            self.env["project.task"]
            .with_user(self.user_projectuser)
            .create({"name": "Private", "user_ids": [Command.set(other.ids)]})
        )
        self.assertEqual(task.sudo().user_ids, other | self.user_projectuser)

    def test_a_private_task_keeps_its_employee_without_a_user(self) -> None:
        if "employee_ids" not in self.env["project.task"]._fields:
            self.skipTest("assignees are employees only with project_hr")
        colleague_user = new_test_user(
            self.env,
            login="k_private_colleague",
            groups="base.group_user,project.group_project_user",
        )
        Employee = self.env["hr.employee"]
        worker = Employee.create({"name": "Worker without a user"})
        colleague = Employee.create({"name": "Colleague", "user_id": colleague_user.id})
        task = (
            self.env["project.task"]
            .with_user(self.user_projectuser)
            .create(
                {
                    "name": "Private",
                    "employee_ids": [Command.set((worker | colleague).ids)],
                }
            )
            .sudo()
        )
        self.assertEqual(task.employee_ids, worker | colleague)
        self.assertEqual(task.user_ids, colleague_user | self.user_projectuser)
