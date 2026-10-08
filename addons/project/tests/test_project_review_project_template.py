from datetime import date, datetime

from odoo.tests import tagged

from .test_project_base import TestProjectCommon


@tagged("post_install", "-at_install")
class TestProjectReviewTemplate(TestProjectCommon):
    def _template(self, name="Template"):
        return self.env["project.project"].create(
            {
                "name": name,
                "is_template": True,
                "date_start": date(2025, 6, 2),
                "date": date(2025, 6, 30),
            }
        )

    def test_sibling_tasks_sharing_a_name_are_scheduled(self) -> None:
        template = self._template()
        first, _second = self.env["project.task"].create(
            [
                {
                    "name": "Twin",
                    "project_id": template.id,
                    "date_start": datetime(2025, 6, 3, 8),
                    "allocated_hours": 2,
                },
                {
                    "name": "Twin",
                    "project_id": template.id,
                    "date_start": datetime(2025, 6, 20, 8),
                    "allocated_hours": 2,
                },
            ]
        )
        self.env["project.task"].create(
            {"name": "Twin", "project_id": template.id, "parent_id": first.id}
        )
        project = template.action_create_from_template({"date_start": date(2025, 9, 1)})
        copies = project.task_ids.filtered(
            lambda t: t.name == "Twin" and not t.parent_id
        )
        self.assertEqual(len(copies), 2)
        self.assertTrue(all(copies.mapped("date_start")))
        early, late = copies.sorted("date_start")
        self.assertLess(early.date_start, late.date_start)

    def test_template_pairs_follow_copy_order(self) -> None:
        template = self._template()
        tasks = self.env["project.task"].create(
            [
                {"name": "Same", "project_id": template.id, "priority": "1"},
                {"name": "Same", "project_id": template.id, "priority": "0"},
            ]
        )
        project = template.with_context(copy_from_template=True).copy()
        pairs = list(template._get_template_task_pairs(project))
        self.assertEqual({original for original, _copy in pairs}, set(tasks))
        for original, copy in pairs:
            self.assertEqual(original.priority, copy.priority)

    def test_create_from_template_returns_a_record_in_the_callers_context(
        self,
    ) -> None:
        project = self._template().action_create_from_template()
        self.assertNotIn("copy_from_template", project.env.context)
        self.assertNotIn("copy_from_project_template", project.env.context)

    def test_create_from_template_keeps_name_translations(self) -> None:
        self.env["res.lang"]._activate_lang("fr_FR")
        template = self._template("Modele EN")
        template.update_field_translations("name", {"fr_FR": "Modèle FR"})
        project = template.action_create_from_template()
        self.assertEqual(project.with_context(lang="fr_FR").name, "Modèle FR")

    def test_plain_copy_suffixes_name_translations(self) -> None:
        self.env["res.lang"]._activate_lang("fr_FR")
        project = self.env["project.project"].create({"name": "Plain EN"})
        project.update_field_translations("name", {"fr_FR": "Plain FR"})
        copy = project.copy()
        self.assertEqual(copy.name, "Plain EN (copy)")
        self.assertIn("Plain FR", copy.with_context(lang="fr_FR").name)
        self.assertNotEqual(copy.with_context(lang="fr_FR").name, "Plain FR")

    def test_undo_callbacks_do_not_archive(self) -> None:
        project = self.env["project.project"].create({"name": "Source"})
        callbacks = project._get_template_from_project_undo_callbacks()
        self.assertTrue(project.active)
        self.assertEqual(callbacks, {"unarchive_project": True})

    def test_creating_a_template_archives_the_source(self) -> None:
        project = self.env["project.project"].create({"name": "Source"})
        action = project.action_create_template_from_project()
        self.assertFalse(project.active)
        template_id = action["params"]["project_id"]
        self.assertEqual(
            action["params"]["undo_args"],
            [project.id, template_id, {"unarchive_project": True}],
        )

    def test_undoing_a_template_creation_is_one_call(self) -> None:
        project = self.env["project.project"].create({"name": "Source"})
        params = project.action_create_template_from_project()["params"]
        template = self.env["project.project"].browse(params["project_id"])
        result = project.action_undo_create_template_from_project(
            *params["undo_args"][1:]
        )
        self.assertFalse(template.exists())
        self.assertTrue(project.active)
        self.assertEqual(result["tag"], "display_notification")

    def test_undo_never_deletes_a_regular_project(self) -> None:
        project = self.env["project.project"].create({"name": "Source"})
        bystander = self.env["project.project"].create({"name": "Bystander"})
        project.action_undo_create_template_from_project(bystander.id, {})
        self.assertTrue(bystander.exists())
