from odoo import Command

from odoo.addons.project.tests.test_project_sharing import TestProjectSharingCommon


class TestDescriptionTemplateProjectSharing(TestProjectSharingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project_portal.write(
            {
                "collaborator_ids": [
                    Command.create(
                        {
                            "partner_id": cls.user_portal.partner_id.id,
                            "access_mode": "edit",
                        }
                    ),
                ],
            }
        )
        cls.template = cls.env["project.task.description.template"].create(
            {
                "name": "Tpl Sharing",
                "description": "<p>SHARED BODY</p>",
                "project_ids": [Command.set(cls.project_portal.ids)],
            }
        )

    def test_a_collaborator_creates_a_task_in_project_sharing(self):
        Task = self.env["project.task"].with_context(
            default_project_id=self.project_portal.id
        )
        with self.get_project_sharing_form_view(Task, self.user_portal) as form:
            form.name = "Shared task"
        task = form.record.sudo()
        self.assertEqual(task.project_id, self.project_portal)
        self.assertFalse(task.description_template_id)

    def test_a_collaborator_adds_a_subtask_to_a_task_that_holds_a_template(self):
        self.task_portal.description_template_id = self.template
        with self.get_project_sharing_form_view(
            self.task_portal, self.user_portal
        ) as form:
            with form.child_ids.new() as subtask_form:
                subtask_form.name = "Subtask by the collaborator"
        self.assertEqual(self.task_portal.child_ids.name, "Subtask by the collaborator")
        self.assertEqual(self.task_portal.description_template_id, self.template)
