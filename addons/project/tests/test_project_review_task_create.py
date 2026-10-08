from odoo import Command

from .test_project_base import TestProjectCommon


class TestTaskCreateSubscriptions(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.project_pigs.privacy_visibility = "portal"
        cls.project_pigs.partner_id = cls.partner_1

    def _task_links(self, tasks):
        return (
            self.env["access.link"]
            .sudo()
            .search([("res_model", "=", "project.task"), ("res_id", "in", tasks.ids)])
        )

    def test_creating_tasks_in_a_shared_project_issues_no_link(self) -> None:
        tasks = (
            self.env["project.task"]
            .with_user(self.user_projectmanager)
            .create(
                [
                    {"name": f"T{i}", "project_id": self.project_pigs.id}
                    for i in range(3)
                ]
            )
        )
        self.assertFalse(self._task_links(tasks))
        self.assertFalse(any(tasks.mapped("access_token")))

    def test_a_portal_reader_cannot_read_a_task_token(self) -> None:
        self.task_1._portal_get_or_create_token()
        self.assertTrue(self.task_1.access_token)
        self.assertNotIn(
            "access_token", self.env["project.task"].TASK_PORTAL_READABLE_FIELDS
        )

    def test_subtasks_inherit_their_parents_followers_with_subtypes(self) -> None:
        note = self.env.ref("mail.mt_note")
        comment = self.env.ref("mail.mt_comment")
        parent_a, parent_b = self.env["project.task"].create(
            [
                {"name": "A", "project_id": self.project_pigs.id},
                {"name": "B", "project_id": self.project_pigs.id},
            ]
        )
        parent_a.message_subscribe(self.partner_2.ids, note.ids)
        parent_b.message_subscribe(self.partner_3.ids, comment.ids)
        children = (
            self.env["project.task"]
            .with_user(self.user_projectmanager)
            .create(
                [
                    {"name": "a1", "parent_id": parent_a.id},
                    {"name": "a2", "parent_id": parent_a.id},
                    {"name": "b1", "parent_id": parent_b.id},
                ]
            )
        )
        for child in children:
            parent = child.parent_id
            self.assertEqual(
                {
                    f.partner_id: f.subtype_ids
                    for f in child.message_follower_ids
                    if f.partner_id != self.user_projectmanager.partner_id
                },
                {
                    f.partner_id: f.subtype_ids
                    for f in parent.message_follower_ids
                    if f.partner_id.active
                },
            )
            self.assertIn(
                self.user_projectmanager.partner_id, child.message_partner_ids
            )
        self.assertNotIn(self.partner_3, children[:2].message_partner_ids)

    def test_each_subtask_takes_its_own_parents_project(self) -> None:
        parent_pigs, parent_goats = self.env["project.task"].create(
            [
                {"name": "P", "project_id": self.project_pigs.id},
                {"name": "G", "project_id": self.project_goats.id},
            ]
        )
        sub_pigs, sub_goats, private = self.env["project.task"].create(
            [
                {"name": "sp", "parent_id": parent_pigs.id},
                {"name": "sg", "parent_id": parent_goats.id},
                {"name": "private", "user_ids": [Command.link(self.env.uid)]},
            ]
        )
        self.assertEqual(sub_pigs.project_id, self.project_pigs)
        self.assertEqual(sub_goats.project_id, self.project_goats)
        self.assertFalse(private.project_id)
        self.assertFalse(private.step_id)

    def test_a_single_parent_does_not_leak_its_project_to_its_batch(self) -> None:
        parent = self.env["project.task"].create(
            {"name": "P", "project_id": self.project_pigs.id}
        )
        _sub, private = self.env["project.task"].create(
            [
                {"name": "s", "parent_id": parent.id},
                {"name": "private", "user_ids": [Command.link(self.env.uid)]},
            ]
        )
        self.assertFalse(private.project_id)
        self.assertFalse(private.company_id)

    def test_cc_is_matched_on_the_normalized_address(self) -> None:
        self.user_projectuser.partner_id.email = "Armande.ProjectUser@Example.com"
        task = self.env["project.task"].create(
            {
                "name": "cc",
                "project_id": self.project_pigs.id,
                "email_cc": '"Armande" <armande.projectuser@example.com>',
            }
        )
        self.assertIn(self.user_projectuser.partner_id, task.message_partner_ids)

    def test_assignees_follow_without_one_lookup_per_task(self) -> None:
        tasks = self.env["project.task"].create(
            [
                {
                    "name": f"U{i}",
                    "project_id": self.project_pigs.id,
                    "user_ids": [Command.link(self.user_projectuser.id)],
                }
                for i in range(5)
            ]
        )
        for task in tasks:
            self.assertIn(self.user_projectuser.partner_id, task.message_partner_ids)
