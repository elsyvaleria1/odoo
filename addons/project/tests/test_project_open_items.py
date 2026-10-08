from odoo import Command
from odoo.exceptions import ValidationError
from odoo.modules.module import get_module_path, load_script
from odoo.tests import Form, tagged

from .test_project_task_dependency_types import TestDependencyTypesCommon

MIGRATIONS = f"{get_module_path('project')}/migrations/1.33"
DEPENDENCY_SCRIPT = "project_1_33_post_migrate_task_dependencies"
SHARING_SCRIPT = "project_1_33_post_migrate_sharing_rule"


@tagged("post_install", "-at_install")
class TestEnteredStepPreviewAgreesWithSave(TestDependencyTypesCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        Step = cls.env["project.workflow.step"]
        project_link = [Command.link(cls.project.id)]
        cls.done_step = Step.create(
            {"name": "Finished", "task_state": "done", "project_ids": project_link}
        )
        cls.cancel_step = Step.create(
            {"name": "Dropped", "task_state": "canceled", "project_ids": project_link}
        )
        cls.doing_step = Step.create(
            {"name": "Doing", "task_state": "in_progress", "project_ids": project_link}
        )
        cls.backlog_step = Step.create(
            {"name": "Backlog", "task_state": "todo", "project_ids": project_link}
        )
        cls.plain_step = Step.create({"name": "Plain", "project_ids": project_link})

    def _waiting_task(self, dependency_type="fs"):
        predecessor, successor = self._task("P"), self._task("S")
        self._link(successor, predecessor, dependency_type)
        return predecessor, successor

    def test_a_waiting_task_previewed_into_a_done_step_shows_done(self) -> None:
        _predecessor, successor = self._waiting_task()
        self.assertEqual(successor.state, "blocked")
        with Form(successor) as form:
            form.step_id = self.done_step
            self.assertEqual(form.state, "done")
        self.assertEqual(successor.state, "done")

    def test_a_waiting_task_previewed_into_a_cancel_step_shows_cancelled(
        self,
    ) -> None:
        _predecessor, successor = self._waiting_task()
        with Form(successor) as form:
            form.step_id = self.cancel_step
            self.assertEqual(form.state, "canceled")
        self.assertEqual(successor.state, "canceled")

    def test_a_waiting_task_previewed_into_an_open_step_stays_waiting(self) -> None:
        _predecessor, successor = self._waiting_task()
        with Form(successor) as form:
            form.step_id = self.doing_step
            self.assertEqual(form.state, "blocked")
        self.assertEqual(successor.state, "blocked")

    def test_a_preview_back_from_a_done_step_waits_again(self) -> None:
        _predecessor, successor = self._waiting_task()
        with Form(successor) as form:
            form.step_id = self.done_step
            self.assertEqual(form.state, "done")
            form.step_id = self.backlog_step
            self.assertEqual(form.state, "blocked")
        self.assertEqual(successor.state, "blocked")

    def test_an_approved_task_previewed_into_a_plain_step_shows_in_progress(
        self,
    ) -> None:
        task = self._task("T", state="approved")
        with Form(task) as form:
            form.step_id = self.plain_step
            self.assertEqual(form.state, "in_progress")
        self.assertEqual(task.state, "in_progress")

    def test_an_open_finish_predecessor_still_refuses_the_saved_move(self) -> None:
        _predecessor, successor = self._waiting_task("ff")
        form = Form(successor)
        form.step_id = self.done_step
        self.assertEqual(form.state, "done")
        with self.assertRaises(ValidationError):
            form.save()

    def test_a_task_created_in_a_done_step_behind_an_open_start_link_is_done(
        self,
    ) -> None:
        predecessor = self._task("P")
        task = self._task(
            "S",
            step_id=self.done_step.id,
            predecessor_ids=[Command.link(predecessor.id)],
        )
        self.assertEqual(task.dependency_ids.dependency_type, "fs")
        self.assertEqual(task.state, "done")

    def test_a_task_created_in_an_open_step_behind_an_open_start_link_waits(
        self,
    ) -> None:
        predecessor = self._task("P")
        task = self._task(
            "S",
            step_id=self.doing_step.id,
            predecessor_ids=[Command.link(predecessor.id)],
        )
        self.assertEqual(task.state, "blocked")

    def test_a_task_created_in_a_done_step_behind_an_open_finish_link_is_refused(
        self,
    ) -> None:
        predecessor = self._task("P")
        with self.assertRaises(ValidationError):
            self._task(
                "S",
                step_id=self.done_step.id,
                dependency_ids=[
                    Command.create(
                        {"depends_on_id": predecessor.id, "dependency_type": "ff"}
                    )
                ],
            )

    def test_a_new_task_form_in_a_done_step_behind_an_open_link_saves_done(
        self,
    ) -> None:
        predecessor = self._task("P")
        form = Form(
            self.env["project.task"].with_context(default_project_id=self.project.id)
        )
        form.name = "S"
        form.predecessor_ids.add(predecessor)
        form.step_id = self.doing_step
        self.assertEqual(form.state, "blocked")
        form.step_id = self.done_step
        self.assertEqual(form.state, "done")
        task = form.save()
        self.assertEqual(task.state, "done")
        self.assertEqual(task.predecessor_ids, predecessor)


@tagged("post_install", "-at_install")
class TestLegacyDependencyCycles(TestDependencyTypesCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.script = load_script(
            f"{MIGRATIONS}/post-migrate_task_dependencies.py", DEPENDENCY_SCRIPT
        )

    def test_the_link_closing_a_cycle_is_dropped_in_task_order(self) -> None:
        split = self.script.split_cycle_closing_links
        self.assertEqual(split([], [(2, 1), (1, 2)]), ([(1, 2)], [(2, 1)]))
        self.assertEqual(
            split([], [(3, 1), (1, 2), (2, 3)]), ([(1, 2), (2, 3)], [(3, 1)])
        )
        self.assertEqual(split([], [(4, 4)]), ([], [(4, 4)]))
        self.assertEqual(
            split([(2, 1)], [(1, 2), (2, 1), (3, 1)]), ([(3, 1)], [(1, 2)])
        )
        self.assertEqual(
            split([], [(1, 2), (1, 3), (2, 3), (4, 1)]),
            ([(1, 2), (1, 3), (2, 3), (4, 1)], []),
        )

    def _seed_legacy_relation(self, links) -> None:
        self.env.flush_all()
        cr = self.env.cr
        cr.execute(
            """
            CREATE TABLE project_task_dependency_rel (
                task_id integer NOT NULL REFERENCES project_task ON DELETE CASCADE,
                depends_on_id integer NOT NULL REFERENCES project_task ON DELETE CASCADE,
                PRIMARY KEY (task_id, depends_on_id)
            )
            """
        )
        cr.execute(
            """
            INSERT INTO project_task_dependency_rel (task_id, depends_on_id)
            SELECT * FROM unnest(%s::int[], %s::int[])
            """,
            [[t.id for t, _ in links], [d.id for _, d in links]],
        )
        tasks = self.env["project.task"].union(*(t | d for t, d in links))
        cr.execute(
            "UPDATE project_task SET state = 'blocked' WHERE id = ANY(%s)",
            [tasks.ids],
        )
        self.env.invalidate_all()

    def _typed_links(self, tasks):
        self.env.cr.execute(
            """
            SELECT task_id, depends_on_id FROM project_task_dependency
             WHERE task_id = ANY(%s) ORDER BY task_id, depends_on_id
            """,
            [tasks.ids],
        )
        return self.env.cr.fetchall()

    def test_legacy_cycles_migrate_acyclic_and_unblocked(self) -> None:
        a, b, c, d, e, f, g = (self._task(name) for name in "ABCDEFG")
        self._link(f, g)
        self.env.flush_all()
        self._seed_legacy_relation([(a, b), (b, a), (c, d), (d, e), (e, c), (g, f)])

        with self.assertLogs(DEPENDENCY_SCRIPT, "WARNING") as logs:
            self.script.migrate(self.env.cr, "19.0.1.32")

        self.env.invalidate_all()
        tasks = a | b | c | d | e | f | g
        self.assertEqual(
            self._typed_links(tasks),
            [(a.id, b.id), (c.id, d.id), (d.id, e.id), (f.id, g.id)],
        )
        self.assertEqual(len(logs.records), 3)
        for (task, predecessor), record in zip(
            [(b, a), (e, c), (g, f)], logs.records, strict=True
        ):
            self.assertEqual(record.args, (task.id, predecessor.id))
        self.assertEqual(
            [task.state for task in tasks],
            [
                "blocked",
                "in_progress",
                "blocked",
                "blocked",
                "in_progress",
                "blocked",
                "in_progress",
            ],
        )
        self.env.cr.execute(
            "SELECT 1 FROM pg_tables WHERE tablename = 'project_task_dependency_rel'"
        )
        self.assertFalse(self.env.cr.fetchall())


@tagged("post_install", "-at_install")
class TestSharingRuleActivatedOnce(TestDependencyTypesCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.script = load_script(
            f"{MIGRATIONS}/post-migrate_sharing_rule_last_update.py", SHARING_SCRIPT
        )
        cls.rule = cls.env.ref("project.project_task_rule_portal_project_sharing")

    def test_a_1_31_database_gets_the_rule_activated(self) -> None:
        self.rule.active = False
        self.script.migrate(self.env.cr, "19.0.1.31")
        self.assertTrue(self.rule.active)

    def test_a_rule_turned_off_after_the_toggle_went_stays_off(self) -> None:
        self.rule.active = False
        self.script.migrate(self.env.cr, "19.0.1.32")
        self.assertFalse(self.rule.active)

    def test_a_1_32_database_that_still_toggled_gets_the_rule_activated(
        self,
    ) -> None:
        self.env["ir.model.data"].create(
            {
                "module": "project",
                "name": "privilege_manage_feature_groups",
                "model": "res.groups",
                "res_id": self.env.ref("base.group_user").id,
            }
        )
        self.rule.active = False
        self.env.flush_all()
        self.script.migrate(self.env.cr, "19.0.1.32")
        self.assertTrue(self.rule.active)
