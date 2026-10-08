from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from odoo.addons.project.tests.test_project_base import TestProjectCommon

WIZARD = "wizard.project.column.delete"


@tagged("-at_install", "post_install")
class TestProjectColumnModels(TestProjectCommon):
    def test_every_column_model_is_a_project_column(self) -> None:
        self.assertNotIn("mixin.project.pm", self.env.registry)
        Column = self.env.registry["mixin.project.column"]
        Container = self.env.registry["mixin.project.column.container"]
        for name in ("project.phase", "project.workflow.step", "project.triage"):
            self.assertIsInstance(self.env[name], Column, name)
        for name in ("project.phase", "project.workflow.step"):
            self.assertIsInstance(self.env[name], Container, name)
        self.assertNotIsInstance(self.env["project.triage"], Container)
        self.assertNotIn("is_archive_recorded", self.env["project.triage"]._fields)

    def test_a_step_refuses_a_template_about_another_model(self) -> None:
        template = self.env["mail.template"].create(
            {
                "name": "About a project",
                "model_id": self.env.ref("project.model_project_project").id,
            }
        )
        step = self.env["project.workflow.step"].create({"name": "Step"})
        with self.assertRaises(ValidationError):
            step.mail_template_id = template

    def test_archiving_with_archived_records_in_view_spares_them(self) -> None:
        step = self.env["project.workflow.step"].create(
            {"name": "Own", "project_ids": self.project_pigs.ids}
        )
        Task = self.env["project.task"]
        held = Task.create(
            {"name": "Held", "project_id": self.project_pigs.id, "step_id": step.id}
        )
        shelved = Task.create(
            {"name": "Shelved", "project_id": self.project_pigs.id, "step_id": step.id}
        )
        shelved.active = False
        step.with_user(self.user_projectuser).with_context(
            active_test=False
        ).action_archive()
        self.assertFalse(held.active)
        self.assertEqual(step.archived_member_ids, held)


@tagged("-at_install", "post_install")
class TestProjectColumnDeleteWizard(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.phase = cls.env["project.phase"].create({"name": "Closing"})
        cls.step = cls.env["project.workflow.step"].create(
            {
                "name": "Shared",
                "project_ids": [
                    Command.link(cls.project_pigs.id),
                    Command.link(cls.project_goats.id),
                ],
            }
        )

    def _open(self, columns, user=None, **kwargs):
        if user:
            columns = columns.with_user(user)
        action = columns.action_open_delete_wizard(**kwargs)
        wizard = (
            self.env[action["res_model"]]
            .with_user(user or self.env.user)
            .with_context(action["context"])
            .browse(action["res_id"])
        )
        return action, wizard

    def test_one_wizard_serves_phases_and_steps(self) -> None:
        self.assertNotIn("wizard.project.phase.delete", self.env.registry)
        self.assertNotIn("wizard.project.workflow.step.delete", self.env.registry)
        for column in (self.phase, self.step):
            action, wizard = self._open(column)
            self.assertEqual(action["res_model"], WIZARD)
            self.assertEqual(action["target"], "new")
            self.assertEqual(wizard.res_model, column._name)
            self.assertEqual(wizard.res_ids, column.ids)

    def test_the_wizard_takes_only_container_columns(self) -> None:
        triage = self.env["project.triage"].create({"name": "Later"})
        for model, ids in (("project.triage", triage.ids), ("res.partner", [1])):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                self.env[WIZARD].create({"res_model": model, "res_ids": ids})

    def test_the_member_count_follows_the_columns(self) -> None:
        Task = self.env["project.task"]
        Task.create(
            {"name": "A", "project_id": self.project_pigs.id, "step_id": self.step.id}
        )
        archived = Task.create(
            {"name": "B", "project_id": self.project_goats.id, "step_id": self.step.id}
        )
        archived.active = False
        _action, wizard = self._open(self.step)
        self.assertEqual(wizard.count_member, 2)
        self.assertTrue(wizard.is_columns_active)
        self.assertEqual(wizard.project_ids, self.project_pigs | self.project_goats)
        wizard.res_ids = []
        self.assertEqual(wizard.count_member, 0)

    def test_the_message_names_the_column_and_its_members(self) -> None:
        _action, wizard = self._open(self.phase)
        self.assertIn("phases", wizard.message)
        self.env["project.project"].create({"name": "Held", "phase_id": self.phase.id})
        wizard.invalidate_recordset(["count_member", "message"])
        self.assertIn("projects", wizard.message)
        _action, wizard = self._open(self.step)
        self.assertIn("workflow steps", wizard.message)
        self.assertFalse(self._open(self.phase)[1].project_ids)

    def test_archiving_a_phase_cascades_to_its_projects(self) -> None:
        self.user_projectmanager.group_ids += self.env.ref(
            "project.group_project_stages"
        )
        project = self.env["project.project"].create(
            {"name": "Held", "phase_id": self.phase.id}
        )
        _action, wizard = self._open(self.phase, user=self.user_projectmanager)
        self.assertEqual(wizard.count_member, 1)
        result = wizard.action_archive()
        self.assertFalse(self.phase.active)
        self.assertFalse(project.active)
        self.assertEqual(result["type"], "ir.actions.act_window_close")
        self.assertTrue(result["infos"]["success"])

    def test_a_project_user_cannot_archive_a_phase_through_the_wizard(self) -> None:
        self.env["project.project"].create({"name": "Held", "phase_id": self.phase.id})
        _action, wizard = self._open(self.phase, user=self.user_projectuser)
        with self.assertRaises(AccessError):
            wizard.action_archive()
        self.assertTrue(self.phase.active)

    def test_an_empty_step_is_deleted_and_the_list_reopened(self) -> None:
        step = self.env["project.workflow.step"].create(
            {"name": "Empty", "project_ids": self.project_pigs.ids}
        )
        _action, wizard = self._open(
            step, user=self.user_projectmanager, stage_view=True
        )
        result = wizard.action_unlink()
        self.assertFalse(step.exists())
        self.assertEqual(result["res_model"], "project.workflow.step")
        self.assertEqual(result["target"], "main")
        self.assertTrue(result["context"]["active_test"])

    def test_an_empty_phase_deleted_from_its_list_reopens_the_phases(self) -> None:
        _action, wizard = self._open(
            self.phase, user=self.user_projectmanager, stage_view=True
        )
        result = wizard.action_unlink()
        self.assertFalse(self.phase.exists())
        self.assertEqual(
            result["id"], self.env.ref("project.project_phase_configure").id
        )
