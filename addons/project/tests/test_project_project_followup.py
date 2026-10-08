import re
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged

from .test_project_base import TestProjectCommon


@tagged("post_install", "-at_install")
class TestProjectLastUpdate(TestProjectCommon):
    def _update(self, project, name, status, date, **vals):
        return self.env["project.update"].create(
            {
                "name": name,
                "project_id": project.id,
                "status": status,
                "date": date,
                **vals,
            }
        )

    def test_last_update_is_a_stored_compute_with_no_sync_helper(self) -> None:
        field = self.env["project.project"]._fields["last_update_id"]
        self.assertTrue(field.compute and field.store and field.compute_sudo)
        self.assertFalse(
            hasattr(self.env["project.update"], "_sync_project_last_update")
        )

    def test_a_backdated_update_does_not_replace_a_newer_one(self) -> None:
        today = fields.Date.today()
        newer = self._update(self.project_pigs, "Newer", "off_track", today)
        self._update(self.project_pigs, "Older", "on_track", today - timedelta(5))
        self.assertEqual(self.project_pigs.last_update_id, newer)
        self.assertEqual(self.project_pigs.last_update_status, "off_track")
        self.assertEqual(self.project_pigs.last_update_color, 23)

    def test_same_day_updates_follow_the_newest_record(self) -> None:
        today = fields.Date.today()
        self._update(self.project_pigs, "First", "on_track", today)
        second = self._update(self.project_pigs, "Second", "at_risk", today)
        self.assertEqual(self.project_pigs.last_update_id, second)
        self.assertEqual(self.project_pigs.last_update_status, "at_risk")

    def test_moving_an_update_moves_the_latest_with_it(self) -> None:
        update = self._update(
            self.project_pigs, "Moving", "at_risk", fields.Date.today()
        )
        update.project_id = self.project_goats
        self.assertFalse(self.project_pigs.last_update_id)
        self.assertEqual(self.project_pigs.last_update_status, "to_define")
        self.assertEqual(self.project_pigs.last_update_color, 0)
        self.assertEqual(self.project_goats.last_update_id, update)
        self.assertEqual(self.project_goats.last_update_status, "at_risk")

    def test_the_latest_ignores_what_the_triggering_user_can_read(self) -> None:
        today = fields.Date.today()
        project = self.env["project.project"].create(
            {
                "name": "Hidden",
                "privacy_visibility": "followers",
                "user_id": self.user_projectmanager.id,
            }
        )
        own = self._update(
            project,
            "Own",
            "on_track",
            today - timedelta(10),
            user_id=self.user_projectuser.id,
        )
        newest = self._update(project, "Newest", "off_track", today)
        self.assertFalse(project.with_user(self.user_projectuser).has_access("read"))
        own.with_user(self.user_projectuser).date = today - timedelta(3)
        self.env.flush_all()
        self.assertEqual(project.last_update_id, newest)
        self.assertEqual(project.last_update_status, "off_track")


@tagged("post_install", "-at_install")
class TestProjectHistorySnapshot(TestProjectCommon):
    def _snapshots(self, project):
        return self.env["project.history"].search([("project_id", "=", project.id)])

    def test_the_action_is_named_for_what_it_does(self) -> None:
        Project = self.env["project.project"]
        self.assertTrue(hasattr(Project, "action_snapshot_to_history"))
        self.assertFalse(hasattr(Project, "action_archive_to_history"))
        arch = self.env.ref("project.edit_project").arch
        self.assertIn('name="action_snapshot_to_history"', arch)
        self.assertNotIn("action_archive_to_history", arch)

    def test_a_snapshot_leaves_the_project_active(self) -> None:
        self.project_pigs.action_snapshot_to_history()
        self.assertTrue(self.project_pigs.active)
        self.assertEqual(len(self._snapshots(self.project_pigs)), 1)

    def test_a_project_user_cannot_snapshot(self) -> None:
        with self.assertRaises(AccessError):
            self.project_pigs.with_user(
                self.user_projectuser
            ).action_snapshot_to_history()
        self.assertFalse(self._snapshots(self.project_pigs))

    def test_archiving_snapshots_the_tasks_it_archives(self) -> None:
        self.project_pigs.with_user(self.user_projectmanager).action_archive()
        snapshot = self._snapshots(self.project_pigs)
        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot.task_count, 2)
        self.assertEqual(snapshot.name, self.project_pigs.name)

    def test_archiving_twice_a_day_keeps_one_snapshot(self) -> None:
        self.project_pigs.action_archive()
        self.project_pigs.action_unarchive()
        self.project_pigs.action_archive()
        self.assertEqual(len(self._snapshots(self.project_pigs)), 1)

    def test_archiving_a_template_takes_no_snapshot(self) -> None:
        template = self.env["project.project"].create(
            {"name": "Template", "is_template": True}
        )
        template.action_archive()
        self.assertFalse(self._snapshots(template))


@tagged("post_install", "-at_install")
class TestProjectSharingRulesStayActive(TestProjectCommon):
    def test_the_sharing_rule_stays_active_with_no_collaborator(self) -> None:
        self.assertFalse(
            hasattr(
                self.env["project.collaborator"], "_update_project_sharing_portal_rules"
            )
        )
        project = self.env["project.project"].create(
            {"name": "Shared", "privacy_visibility": "portal"}
        )
        project._add_collaborators(self.partner_2)
        self.env["project.collaborator"].search([]).unlink()
        rule = self.env.ref("project.project_task_rule_portal_project_sharing")
        self.assertTrue(rule.active)

    def test_the_active_rule_gives_a_non_collaborator_nothing(self) -> None:
        project = self.env["project.project"].create(
            {"name": "Followed", "privacy_visibility": "portal"}
        )
        project.message_subscribe(partner_ids=self.user_portal.partner_id.ids)
        self.assertTrue(
            self.env.ref("project.project_task_rule_portal_project_sharing").active
        )
        with self.assertRaises(AccessError):
            self.env["project.task"].with_user(self.user_portal).create(
                {"name": "Intruder", "project_id": project.id}
            )


@tagged("post_install", "-at_install")
class TestProjectFeatureGroups(TestProjectCommon):
    def setUp(self) -> None:
        super().setUp()
        self.group = self.env.ref("project.group_project_milestone")
        self.base_group_user = self.env.ref("base.group_user")
        self.env["project.project"].with_context(active_test=False).search(
            [("allow_milestones", "=", True)]
        ).write({"allow_milestones": False})
        self.assertNotIn(self.group, self.base_group_user.implied_ids)

    def test_the_features_groups_map_each_feature_to_its_group(self) -> None:
        Project = self.env["project.project"]
        employee = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Plain Employee",
                    "login": "plain_employee",
                    "group_ids": [Command.set(self.base_group_user.ids)],
                }
            )
        )
        self.assertEqual(
            Project.with_user(self.user_projectuser).get_features_groups(),
            Project._get_project_features_mapping(),
        )
        self.assertEqual(Project.with_user(employee).get_features_groups(), {})

    def test_the_last_feature_project_leaves_a_hand_given_grant(self) -> None:
        user = self.user_projectuser
        user.write({"group_ids": [Command.link(self.group.id)]})
        project = self.env["project.project"].create(
            {"name": "Milestones", "allow_milestones": True}
        )
        self.assertIn(self.group, self.base_group_user.implied_ids)
        project.action_archive()
        self.assertNotIn(self.group, self.base_group_user.implied_ids)
        self.assertTrue(user.has_group("project.group_project_milestone"))
        self.assertFalse(
            self.user_projectmanager.has_group("project.group_project_milestone")
        )

    def test_a_feature_reaches_everyone_when_its_user_holds_it_by_hand(
        self,
    ) -> None:
        manager = self.user_projectmanager
        manager.write({"group_ids": [Command.link(self.group.id)]})
        self.env["project.project"].with_user(manager).create(
            {"name": "Milestones", "allow_milestones": True}
        )
        self.assertIn(self.group, self.base_group_user.implied_ids)
        self.assertTrue(
            self.user_projectuser.has_group("project.group_project_milestone")
        )


@tagged("post_install", "-at_install")
class TestProjectCopyLeavesCallerValues(TestProjectCommon):
    def test_copy_paths_leave_the_callers_dicts_alone(self) -> None:
        default = {"name": "Copied"}
        self.project_pigs.copy(default)
        self.project_pigs.copy_data(default)
        self.assertEqual(default, {"name": "Copied"})
        today = fields.Date.today()
        template = self.env["project.project"].create(
            {
                "name": "Template",
                "is_template": True,
                "date_start": today,
                "date": today + timedelta(10),
            }
        )
        values = {"name": "From template"}
        template.action_create_from_template(values)
        self.assertEqual(values, {"name": "From template"})

    def test_the_project_follower_helper_is_gone(self) -> None:
        self.assertFalse(hasattr(self.env["project.project"], "_add_followers"))


@tagged("post_install", "-at_install")
class TestProjectLinkTaskChatter(TestProjectCommon, HttpCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.project_pigs.privacy_visibility = "portal"
        cls.token = cls.project_pigs._portal_get_or_create_token()
        cls.other_task = cls.env["project.task"].create(
            {"name": "Elsewhere", "project_id": cls.project_goats.id}
        )

    def _chatter_attributes(self, project, task, token) -> dict[str, str]:
        response = self.url_open(
            f"/my/projects/{project.id}/task/{task.id}?access_token={token}"
        )
        self.assertEqual(response.status_code, 200)
        discussion = re.search(r'<div[^>]*id="discussion"[^>]*>', response.text)
        self.assertTrue(discussion, "the task page renders its chatter")
        return dict(re.findall(r'data-(token|pid|hash)="([^"]*)"', discussion[0]))

    def _post(self, task, body, attributes) -> None:
        self.url_open(
            "/mail/message/post",
            data=json_dumps(
                {
                    "params": {
                        "thread_model": task._name,
                        "thread_id": task.id,
                        "post_data": {"body": body},
                        **attributes,
                    }
                }
            ),
            headers={"Content-Type": "application/json"},
        )

    def _messages(self, task, body):
        return (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", task._name),
                    ("res_id", "=", task.id),
                    ("body", "ilike", body),
                ]
            )
        )

    def test_the_project_link_posts_on_its_task_as_the_links_partner(self) -> None:
        attributes = self._chatter_attributes(
            self.project_pigs, self.task_1, self.token
        )
        self.assertEqual(attributes.get("token"), self.token)
        self.assertEqual(attributes.get("pid"), str(self.partner_1.id))
        self.assertTrue(attributes.get("hash"))
        self._post(self.task_1, "Posted by the project link", attributes)
        message = self._messages(self.task_1, "Posted by the project link")
        self.assertEqual(len(message), 1)
        self.assertEqual(message.author_id, self.partner_1)

    def test_the_project_link_cannot_post_on_another_projects_task(self) -> None:
        attributes = self._chatter_attributes(
            self.project_pigs, self.task_1, self.token
        )
        self._post(self.other_task, "Posted elsewhere", attributes)
        self.assertFalse(self._messages(self.other_task, "Posted elsewhere"))

    def test_a_view_link_gets_no_signature(self) -> None:
        __, view_token = (
            self.env["access.link"]
            .sudo()
            ._issue(self.project_pigs, partner=self.partner_2, role="view")
        )
        attributes = self._chatter_attributes(
            self.project_pigs, self.task_1, view_token
        )
        self.assertFalse(attributes.get("hash"))
        self._post(self.task_1, "Posted by a viewer", {"token": view_token})
        self.assertFalse(self._messages(self.task_1, "Posted by a viewer"))
