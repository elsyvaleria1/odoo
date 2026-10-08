from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import Form

from .test_project_base import TestProjectCommon
from .test_project_sharing import TestProjectSharingCommon


class TestTaskWriteHooks(TestProjectCommon):
    def test_write_leaves_the_callers_values_alone(self) -> None:
        milestone = self.env["project.milestone"].create(
            {"name": "M", "project_id": self.project_pigs.id}
        )
        vals = {
            "milestone_id": milestone.id,
            "description": "<p>d</p>",
            "user_ids": [Command.link(self.user_projectmanager.id)],
        }
        before = dict(vals)
        (self.task_1 | self.task_2).write(vals)
        self.assertEqual(vals, before)

    def test_clearing_assignees_of_an_unassigned_task_stamps_no_date(self) -> None:
        task = self.env["project.task"].create(
            {"name": "u", "project_id": self.project_pigs.id}
        )
        task.write({"user_ids": [Command.clear()]})
        self.assertFalse(task.date_assign)
        task.write({"user_ids": [Command.link(self.user_projectuser.id)]})
        self.assertTrue(task.date_assign)

    def test_only_tasks_changing_project_are_announced(self) -> None:
        self.project_goats.message_subscribe(
            self.partner_3.ids, self.env.ref("project.mt_project_task_new").ids
        )
        staying = self.env["project.task"].create(
            {"name": "staying", "project_id": self.project_goats.id}
        )
        moving = self.task_1

        def transfer_notices(task):
            return self.env["mail.message"].search(
                [
                    ("model", "=", "project.task"),
                    ("res_id", "=", task.id),
                    ("body", "ilike", "Transferred"),
                ]
            )

        (staying | moving).write({"project_id": self.project_goats.id})
        self.assertFalse(transfer_notices(staying))
        self.assertTrue(transfer_notices(moving))

    def test_subscribing_tasks_of_projects_sharing_a_follower(self) -> None:
        for project in self.project_pigs | self.project_goats:
            project.message_subscribe(self.partner_2.ids)
        tasks = self.env["project.task"].create(
            [
                {"name": "p", "project_id": self.project_pigs.id},
                {"name": "g", "project_id": self.project_goats.id},
            ]
        )
        tasks.message_subscribe(self.partner_2.ids)
        for task in tasks:
            self.assertIn(self.partner_2, task.message_partner_ids)

    def test_a_reply_on_a_private_task_subscribes_nobody(self) -> None:
        private = self.env["project.task"].create(
            {"name": "private", "user_ids": [Command.link(self.env.uid)]}
        )
        private.message_update({"to": self.partner_2.email, "cc": self.partner_3.email})
        self.assertNotIn(self.partner_2, private.message_partner_ids)
        self.assertNotIn(self.partner_3, private.message_partner_ids)
        shared = self.task_1
        shared.message_update({"to": self.partner_2.email})
        self.assertIn(self.partner_2, shared.message_partner_ids)

    def test_mail_recipients_match_on_normalized_email_and_tolerate_no_alias(
        self,
    ) -> None:
        self.user_projectuser.partner_id.email = "Armande.ProjectUser@Example.com"
        self.project_pigs.alias_name = False
        internal, without_users, unmatched = self.env[
            "project.task"
        ]._get_internal_users_from_address_mail(
            "armande.projectuser@example.com, stranger@example.com",
            self.project_pigs.id,
        )
        self.assertEqual(internal, self.user_projectuser.ids)
        self.assertFalse(without_users)
        self.assertEqual(unmatched, ["stranger@example.com"])


class TestPortalTaskCreateMoves(TestProjectSharingCommon):
    def test_an_edit_collaborator_cannot_create_into_a_chosen_step(self) -> None:
        self.project_portal.write(
            {
                "collaborator_ids": [
                    Command.create(
                        {
                            "partner_id": self.user_portal.partner_id.id,
                            "access_mode": "edit",
                        }
                    )
                ]
            }
        )
        done = self.project_portal.workflow_step_ids.filtered(
            lambda s: s.name == "Done"
        )
        Task = (
            self.env["project.task"]
            .with_user(self.user_portal)
            .with_context(default_project_id=self.project_portal.id)
        )
        Task.create({"name": "plain"})
        with self.assertRaises(AccessError):
            Task.create({"name": "moved", "step_id": done.id})
        with self.assertRaises(AccessError):
            Task.create({"name": "urgent", "priority": "3"})


class TestTaskSearchesAndWarnings(TestProjectCommon):
    def test_undated_tasks_are_found_by_effective_start(self) -> None:
        undated = self.env["project.task"].create(
            {"name": "undated", "project_id": self.project_pigs.id}
        )
        dated = self.env["project.task"].create(
            {
                "name": "dated",
                "project_id": self.project_pigs.id,
                "date_end": "2026-01-10 10:00:00",
            }
        )
        found = self.env["project.task"].search(
            [("id", "in", (undated | dated).ids), ("date_start_effective", "=", False)]
        )
        self.assertEqual(found, undated)
        found = self.env["project.task"].search(
            [("id", "in", (undated | dated).ids), ("date_start_effective", "!=", False)]
        )
        self.assertEqual(found, dated)

    def test_a_dependency_warning_survives_an_onchange(self) -> None:
        self.project_pigs.allow_dependencies = True
        predecessor = self.env["project.task"].create(
            {
                "name": "pred",
                "project_id": self.project_pigs.id,
                "date_start": "2026-01-01 08:00:00",
                "date_end": "2026-01-10 18:00:00",
            }
        )
        task = self.env["project.task"].create(
            {
                "name": "task",
                "project_id": self.project_pigs.id,
                "date_start": "2026-01-05 08:00:00",
                "date_end": "2026-01-06 18:00:00",
                "predecessor_ids": [Command.link(predecessor.id)],
            }
        )
        self.assertTrue(task.dependency_warning)
        edited = task.new({"date_end": task.date_end}, origin=task)
        self.assertTrue(edited.dependency_warning)
        with Form(task) as form:
            form.date_end = "2026-01-12 18:00:00"
            self.assertTrue(form.dependency_warning)
            form.date_start = "2026-01-11 08:00:00"
            self.assertFalse(form.dependency_warning)
        self.assertNotIn(
            task,
            self.env["project.task"].search([("dependency_warning", "!=", False)]),
        )

    def test_comodel_search_keeps_a_list_of_names(self) -> None:
        users = self.env["project.task"]._search_on_comodel(
            [("user_ids", "in", ["Armande ProjectUser"])], "user_ids", "res.users"
        )
        self.assertEqual(users, self.user_projectuser)


class TestQuickCreateLookups(TestProjectCommon):
    def _quick_create(self, title):
        return (
            self.env["project.task"]
            .with_context(default_project_id=self.project_pigs.id)
            .create({"display_name": title})
        )

    def test_a_mention_never_assigns_a_portal_user(self) -> None:
        self.user_portal.name = "Chell Unique"
        self.assertFalse(self._quick_create("Feed @Chell").user_ids)

    def test_a_tag_with_wildcards_is_not_matched_loosely(self) -> None:
        existing = self.env["project.tags"].create({"name": "axb"})
        tags = self._quick_create("Feed #a_b").tag_ids
        self.assertNotIn(existing, tags)
        self.assertEqual(tags.mapped("name"), ["a_b"])

    def test_calendar_defaults_with_several_users(self) -> None:
        vals = (
            self.env["project.task"]
            .with_context(
                scale="month",
                date_start="2026-01-05 08:00:00",
                date_end="2026-01-05 17:00:00",
                user_ids=[self.user_projectuser.id, self.user_projectmanager.id],
            )
            .default_get(["date_start", "date_end"])
        )
        self.assertTrue(vals.get("date_start"))


class TestProjectSharingThreadAccess(TestProjectSharingCommon):
    def test_a_collaborator_reaches_only_tasks_of_the_shared_project(self) -> None:
        self.project_portal.write(
            {
                "collaborator_ids": [
                    Command.create({"partner_id": self.user_portal.partner_id.id})
                ]
            }
        )
        Task = self.env["project.task"].with_user(self.user_portal)
        shared_task = self.env["project.task"].create(
            {"name": "shared", "project_id": self.project_portal.id, "active": False}
        )
        self.assertEqual(
            Task._get_thread_with_access(
                shared_task.id, project_sharing_id=self.project_portal.id
            ),
            shared_task,
        )
        self.assertFalse(
            Task._get_thread_with_access(
                self.task_no_collabo.id, project_sharing_id=self.project_portal.id
            )
        )
        self.assertFalse(
            Task._get_thread_with_access(
                self.task_no_collabo.id,
                project_sharing_id=self.task_no_collabo.project_id.id,
            )
        )


class TestPortalUserNamesKeepEdits(TestProjectCommon):
    def test_an_unsaved_assignee_edit_survives_the_names(self) -> None:
        task = self.task_1
        task.user_ids = self.user_projectuser | self.user_projectmanager
        new = task.new(
            {"user_ids": [Command.set(self.user_projectmanager.ids)]}, origin=task
        )
        self.assertEqual(new.portal_user_names, self.user_projectmanager.name)
        self.assertEqual(new.user_ids._origin, self.user_projectmanager)
