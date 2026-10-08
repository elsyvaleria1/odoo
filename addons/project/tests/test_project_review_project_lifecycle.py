from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_project_base import TestProjectCommon


@tagged("post_install", "-at_install")
class TestProjectReviewFeatureGroups(TestProjectCommon):
    def setUp(self) -> None:
        super().setUp()
        self.Project = self.env["project.project"]
        self.group = self.env.ref("project.group_project_milestone")
        self.base_group_user = self.env.ref("base.group_user")
        self.Project.with_context(active_test=False).search(
            [("allow_milestones", "=", True)]
        ).write({"allow_milestones": False})
        self.assertNotIn(self.group, self.base_group_user.implied_ids)

    def test_deleting_the_last_project_using_a_feature_drops_its_group(self) -> None:
        project = self.Project.create({"name": "Last one", "allow_milestones": True})
        self.assertIn(self.group, self.base_group_user.implied_ids)
        project.unlink()
        self.assertNotIn(self.group, self.base_group_user.implied_ids)

    def test_archiving_the_last_project_using_a_feature_drops_its_group(self) -> None:
        project = self.Project.create({"name": "Archived", "allow_milestones": True})
        project.action_archive()
        self.assertNotIn(self.group, self.base_group_user.implied_ids)
        project.action_unarchive()
        self.assertIn(self.group, self.base_group_user.implied_ids)

    def test_feature_mapping_names_every_synced_group(self) -> None:
        mapping = self.Project._get_project_features_mapping()
        self.assertEqual(mapping["allow_milestones"], "project.group_project_milestone")
        self.assertEqual(
            mapping["allow_dependencies"], "project.group_project_task_dependencies"
        )
        self.assertEqual(
            mapping["allow_recurring_tasks"], "project.group_project_recurring_tasks"
        )


@tagged("post_install", "-at_install")
class TestProjectReviewArchive(TestProjectCommon):
    def test_unarchiving_keeps_tasks_archived_on_their_own(self) -> None:
        Task = self.env["project.task"]
        project = self.env["project.project"].create({"name": "Archive"})
        kept, alone = Task.create(
            [
                {"name": "Kept", "project_id": project.id},
                {"name": "Alone", "project_id": project.id},
            ]
        )
        alone.action_archive()
        project.action_archive()
        self.assertFalse(kept.active)
        project.action_unarchive()
        self.assertTrue(kept.active)
        self.assertFalse(alone.active)

    def test_archiving_twice_does_not_forget_what_it_archived(self) -> None:
        Task = self.env["project.task"]
        project = self.env["project.project"].create({"name": "Twice"})
        task = Task.create({"name": "Task", "project_id": project.id})
        project.action_archive()
        project.write({"active": False})
        project.action_unarchive()
        self.assertTrue(task.active)


@tagged("post_install", "-at_install")
class TestProjectReviewWriteContract(TestProjectCommon):
    def test_write_leaves_the_callers_vals_alone(self) -> None:
        vals = {"last_update_status": "on_track", "description": "x"}
        self.project_pigs.write(vals)
        self.assertEqual(vals, {"last_update_status": "on_track", "description": "x"})

    def test_create_returns_records_in_the_callers_context(self) -> None:
        project = self.env["project.project"].create({"name": "Context"})
        self.assertNotIn("mail_create_nosubscribe", project.env.context)

    def test_disabling_dependencies_unblocks_tasks(self) -> None:
        self.project_pigs.allow_dependencies = True
        self.task_1.predecessor_ids = self.task_2
        self.assertEqual(self.task_1.state, "blocked")
        self.project_pigs.write({"allow_dependencies": False})
        self.assertEqual(self.task_1.state, "in_progress")


@tagged("post_install", "-at_install")
class TestProjectReviewAnalyticSharing(TestProjectCommon):
    def setUp(self) -> None:
        super().setUp()
        plan, _other = self.env["account.analytic.plan"]._get_all_plans()
        self.account = self.env["account.analytic.account"].create(
            {"name": "Shared", "plan_id": plan.id}
        )
        self.active_project, self.archived_project = self.env["project.project"].create(
            [
                {"name": "Active", "account_id": self.account.id},
                {"name": "Archived", "account_id": self.account.id},
            ]
        )
        self.archived_project.action_archive()

    def test_deleting_a_project_keeps_an_account_an_archived_one_uses(self) -> None:
        self.active_project.unlink()
        self.assertTrue(self.account.exists())
        self.assertEqual(self.archived_project.account_id, self.account)

    def test_renaming_a_project_keeps_a_shared_account_name(self) -> None:
        self.active_project.name = "Renamed"
        self.assertEqual(self.account.name, "Shared")

    def test_company_change_refused_on_an_account_an_archived_project_shares(
        self,
    ) -> None:
        company = self.env["res.company"].create({"name": "Other Co"})
        self.account.company_id = self.env.company
        with self.assertRaises(UserError):
            self.active_project.company_id = company


@tagged("post_install", "-at_install")
class TestProjectReviewPhase(TestProjectCommon):
    def setUp(self) -> None:
        super().setUp()
        self.env.user.group_ids |= self.env.ref("project.group_project_stages")
        self.company_b = self.env["res.company"].create({"name": "Phase Co"})
        self.env.user.company_ids |= self.company_b
        Phase = self.env["project.phase"]
        self.phase_b = Phase.create(
            {"name": "B only", "sequence": 0, "company_id": self.company_b.id}
        )

    def test_default_phase_never_belongs_to_another_company(self) -> None:
        project = (
            self.env["project.project"]
            .with_user(self.user_projectmanager)
            .create({"name": "No company"})
        )
        self.assertFalse(project.sudo().phase_id.company_id)

    def test_company_change_resets_a_foreign_phase(self) -> None:
        project = self.env["project.project"].create(
            {"name": "B project", "company_id": self.company_b.id}
        )
        project.phase_id = self.phase_b
        project.company_id = self.env.company
        self.assertFalse(project.phase_id.company_id)

    def test_a_user_without_stages_moves_a_project_off_a_foreign_phase(
        self,
    ) -> None:
        project = self.env["project.project"].create(
            {"name": "B project", "company_id": self.company_b.id}
        )
        project.phase_id = self.phase_b
        manager = self.user_projectmanager
        manager.company_ids |= self.company_b
        self.assertFalse(manager.has_group("project.group_project_stages"))
        project.with_user(manager).with_context(
            allowed_company_ids=(self.env.company | self.company_b).ids
        ).company_id = self.env.company
        self.assertEqual(project.company_id, self.env.company)
        self.assertFalse(project.phase_id.company_id)

    def test_clearing_the_company_leaves_no_foreign_phase(self) -> None:
        project = self.env["project.project"].create(
            {"name": "B project", "company_id": self.company_b.id}
        )
        project.phase_id = self.phase_b
        project.company_id = False
        self.assertFalse(project.company_id)
        self.assertFalse(project.phase_id.company_id)

    def test_explicit_phase_in_write_is_kept(self) -> None:
        project = self.env["project.project"].create(
            {"name": "Explicit", "company_id": self.company_b.id}
        )
        project.phase_id = self.phase_b
        other_b = self.env["project.phase"].create(
            {"name": "B second", "sequence": 5, "company_id": self.company_b.id}
        )
        project.write({"company_id": self.company_b.id, "phase_id": other_b.id})
        self.assertEqual(project.phase_id, other_b)

    def test_company_change_resets_only_projects_on_a_foreign_phase(self) -> None:
        on_b, on_shared = self.env["project.project"].create(
            [
                {"name": "On B", "company_id": self.company_b.id},
                {"name": "On shared", "company_id": self.company_b.id},
            ]
        )
        on_b.phase_id = self.phase_b
        later_shared = self.env["project.phase"].create(
            {"name": "Later shared", "sequence": 99}
        )
        on_shared.phase_id = later_shared
        (on_b | on_shared).write({"company_id": self.env.company.id})
        self.assertFalse(on_b.phase_id.company_id)
        self.assertEqual(on_shared.phase_id, later_shared)


@tagged("post_install", "-at_install")
class TestProjectReviewMetrics(TestProjectCommon):
    def test_health_reads_the_pending_risk_state(self) -> None:
        project = self.env["project.project"].create({"name": "Risky"})
        risk = self.env["project.risk"].create(
            {
                "name": "Big",
                "project_id": project.id,
                "probability": "5",
                "impact": "5",
            }
        )
        project.action_reset_metrics()
        self.assertLess(project.health_score, 100)
        risk.write({"state": "resolved", "date_resolved": date.today()})
        project._compute_health_indicators()
        self.assertEqual(project.health_score, 100)

    def test_opening_the_panel_does_not_recompute_metrics(self) -> None:
        with patch.object(
            type(self.project_pigs), "_reset_metrics", autospec=True
        ) as reset:
            self.project_pigs.get_panel_data()
        reset.assert_not_called()

    def test_create_computes_the_snapshot_metrics(self) -> None:
        project = self.env["project.project"].create(
            {"name": "Fresh", "date_start": date(2026, 1, 1), "date": date(2026, 2, 1)}
        )
        self.env["project.task"].create({"name": "WIP", "project_id": project.id})
        project.action_reset_metrics()
        self.assertEqual(project.wip_count, 1)
        empty = self.env["project.project"].create({"name": "Empty"})
        self.assertEqual(empty.health_score, 100)
        self.assertEqual(empty.health_status, "healthy")

    def test_stat_button_counts_closed_tasks(self) -> None:
        self.task_1.state = "done"
        button = self.project_pigs._get_stat_buttons()[0]
        self.assertEqual(button["number"], "1 / 2 (50%)")


@tagged("post_install", "-at_install")
class TestProjectReviewFollowers(TestProjectCommon):
    def test_copy_keeps_each_followers_subtypes(self) -> None:
        note = self.env.ref("mail.mt_note")
        comment = self.env.ref("mail.mt_comment")
        project = self.project_pigs
        project.message_subscribe(partner_ids=self.partner_2.ids, subtype_ids=note.ids)
        project.message_subscribe(
            partner_ids=self.partner_3.ids, subtype_ids=(note | comment).ids
        )
        copy = project.copy()
        followers = {f.partner_id: f.subtype_ids for f in copy.message_follower_ids}
        self.assertEqual(followers[self.partner_2], note)
        self.assertEqual(followers[self.partner_3], note | comment)

    def test_opening_to_portal_subscribes_each_task_customer(self) -> None:
        project = self.env["project.project"].create(
            {"name": "Open", "privacy_visibility": "followers"}
        )
        tasks = self.env["project.task"].create(
            [
                {
                    "name": "A",
                    "project_id": project.id,
                    "partner_id": self.partner_2.id,
                },
                {
                    "name": "B",
                    "project_id": project.id,
                    "partner_id": self.partner_3.id,
                },
                {
                    "name": "C",
                    "project_id": project.id,
                    "partner_id": self.partner_2.id,
                },
            ]
        )
        project.privacy_visibility = "portal"
        for task in tasks:
            self.assertIn(task.partner_id, task.message_partner_ids)


class TestProjectReviewArchiveEmpty(TestProjectCommon):
    def test_a_project_archived_without_active_tasks_restores_none(self) -> None:
        project = self.env["project.project"].create({"name": "Quiet"})
        task = self.env["project.task"].create(
            {"name": "done long ago", "project_id": project.id}
        )
        task.active = False
        project.action_archive()
        project.action_unarchive()
        self.assertFalse(task.active)
