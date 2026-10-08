from datetime import datetime

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import SQL

from odoo.addons.project.tests.test_project_base import TestProjectCommon


@tagged("-at_install", "post_install")
class TestReviewPmChallengeArchiveReach(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        Task = cls.env["project.task"]
        cls.shared_step = cls.env["project.workflow.step"].create(
            {
                "name": "Shared",
                "project_ids": [
                    Command.link(cls.project_pigs.id),
                    Command.link(cls.project_goats.id),
                ],
            }
        )
        cls.visible_task = Task.create(
            {
                "name": "Visible",
                "project_id": cls.project_pigs.id,
                "step_id": cls.shared_step.id,
            }
        )
        cls.private_task = Task.create(
            {
                "name": "Private",
                "project_id": cls.project_goats.id,
                "step_id": cls.shared_step.id,
            }
        )
        cls.own_step = cls.env["project.workflow.step"].create(
            {"name": "Own", "project_ids": [Command.link(cls.project_pigs.id)]}
        )
        cls.own_task = Task.create(
            {
                "name": "Own",
                "project_id": cls.project_pigs.id,
                "step_id": cls.own_step.id,
            }
        )

    def _assert_untouched(self) -> None:
        self.assertTrue(self.shared_step.active)
        self.assertTrue(self.visible_task.active)
        self.assertTrue(self.private_task.active)

    def test_list_archive_of_a_step_shared_out_of_reach_is_refused(self) -> None:
        step = self.shared_step.with_user(self.user_projectuser)

        with self.assertRaises(UserError):
            step.action_archive()

        self._assert_untouched()

    def test_wizard_archive_of_a_step_shared_out_of_reach_is_refused(self) -> None:
        action = self.shared_step.with_user(
            self.user_projectuser
        ).action_open_delete_wizard()
        wizard = (
            self.env[action["res_model"]]
            .with_user(self.user_projectuser)
            .browse(action["res_id"])
        )

        with self.assertRaises(UserError):
            wizard.action_archive()

        self._assert_untouched()

    def test_deleting_a_step_shared_out_of_reach_is_refused(self) -> None:
        step = self.env["project.workflow.step"].create(
            {
                "name": "Empty Shared",
                "project_ids": [
                    Command.link(self.project_pigs.id),
                    Command.link(self.project_goats.id),
                ],
            }
        )
        action = step.with_user(self.user_projectuser).action_open_delete_wizard()
        wizard = (
            self.env[action["res_model"]]
            .with_user(self.user_projectuser)
            .browse(action["res_id"])
        )

        with self.assertRaises(UserError):
            wizard.action_unlink()

        self.assertTrue(step.exists())

    def test_list_and_wizard_archive_cascade_alike_within_reach(self) -> None:
        user = self.user_projectuser
        self.own_step.with_user(user).action_archive()

        self.assertFalse(self.own_step.active)
        self.assertFalse(self.own_task.active)

        self.own_step.with_user(user).action_unarchive()
        action = self.own_step.with_user(user).action_open_delete_wizard()
        self.env[action["res_model"]].with_user(user).browse(
            action["res_id"]
        ).action_archive()

        self.assertFalse(self.own_step.active)
        self.assertFalse(self.own_task.active)

    def test_unarchive_of_a_step_shared_out_of_reach_is_refused(self) -> None:
        self.shared_step.with_user(self.user_projectmanager).action_archive()
        self.assertFalse(self.private_task.active)

        with self.assertRaises(UserError):
            self.shared_step.with_user(self.user_projectuser).action_unarchive()

        self.assertFalse(self.shared_step.active)
        self.assertFalse(self.private_task.active)
        self.shared_step.action_unarchive()
        self.assertTrue(self.private_task.active)
        self.assertTrue(self.visible_task.active)

    def test_phase_archive_with_a_project_out_of_reach_is_refused(self) -> None:
        manager = self.user_projectmanager
        manager.group_ids += self.env.ref("project.group_project_stages")
        other_company = self.env["res.company"].create({"name": "Elsewhere"})
        phase = self.env["project.phase"].create({"name": "Shared Phase"})
        Project = self.env["project.project"]
        reachable = Project.create({"name": "Here", "phase_id": phase.id})
        remote = Project.create(
            {
                "name": "There",
                "phase_id": phase.id,
                "company_id": other_company.id,
            }
        )

        with self.assertRaises(UserError):
            phase.with_user(manager).action_archive()

        self.assertTrue(phase.active)
        self.assertTrue(reachable.active)
        self.assertTrue(remote.active)


@tagged("-at_install", "post_install")
class TestReviewPmChallengeLegacyRestore(TestProjectCommon):
    def _archive_without_recording(self, column, members) -> None:
        self.env.flush_all()
        for records in (members, column):
            self.env.cr.execute(
                SQL(
                    "UPDATE %s SET active = FALSE WHERE id = ANY(%s)",
                    SQL.identifier(records._table),
                    records.ids,
                )
            )
        self.env.invalidate_all()

    def test_a_step_archived_before_the_upgrade_restores_its_tasks(self) -> None:
        step = self.env["project.workflow.step"].create(
            {"name": "Legacy", "project_ids": [Command.link(self.project_pigs.id)]}
        )
        tasks = self.env["project.task"].create(
            [
                {"name": name, "project_id": self.project_pigs.id, "step_id": step.id}
                for name in ("L1", "L2")
            ]
        )
        self._archive_without_recording(step, tasks)

        step.action_unarchive()

        self.assertTrue(step.active)
        self.assertEqual(tasks.mapped("active"), [True, True])

    def test_a_phase_archived_before_the_upgrade_restores_its_projects(self) -> None:
        self.user_projectmanager.group_ids += self.env.ref(
            "project.group_project_stages"
        )
        phase = self.env["project.phase"].create({"name": "Legacy Phase"})
        project = self.env["project.project"].create(
            {"name": "Legacy Project", "phase_id": phase.id}
        )
        self._archive_without_recording(phase, project)

        phase.with_user(self.user_projectmanager).action_unarchive()

        self.assertTrue(phase.active)
        self.assertTrue(project.active)

    def test_a_step_archived_empty_keeps_its_shelved_tasks(self) -> None:
        step = self.env["project.workflow.step"].create(
            {"name": "Empty", "project_ids": [Command.link(self.project_pigs.id)]}
        )
        shelved = self.env["project.task"].create(
            {"name": "Shelved", "project_id": self.project_pigs.id, "step_id": step.id}
        )
        shelved.active = False

        step.action_archive()
        step.action_unarchive()

        self.assertFalse(shelved.active)

    def test_a_legacy_step_shared_out_of_reach_is_not_restored(self) -> None:
        step = self.env["project.workflow.step"].create(
            {
                "name": "Legacy Shared",
                "project_ids": [
                    Command.link(self.project_pigs.id),
                    Command.link(self.project_goats.id),
                ],
            }
        )
        private = self.env["project.task"].create(
            {"name": "P", "project_id": self.project_goats.id, "step_id": step.id}
        )
        self._archive_without_recording(step, private)

        with self.assertRaises(UserError):
            step.with_user(self.user_projectuser).action_unarchive()

        self.assertFalse(step.active)
        self.assertFalse(private.active)


@tagged("-at_install", "post_install")
class TestReviewPmChallengeGateMilestone(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.project_pigs.allow_milestones = True
        cls.milestone = cls.env["project.milestone"].create(
            {"name": "M", "project_id": cls.project_pigs.id, "is_reached": True}
        )
        cls.gate = cls.env["project.gate"].create(
            {
                "name": "G",
                "project_id": cls.project_pigs.id,
                "milestone_id": cls.milestone.id,
                "criterion_ids": [Command.create({"name": "Scope", "is_met": True})],
            }
        )
        cls.gate.action_pass()

    def test_un_reaching_the_milestone_of_a_passed_gate_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            self.milestone.is_reached = False

        with self.assertRaises(ValidationError):
            self.milestone.update_is_reached(False)

        self.assertEqual(self.gate.state, "passed")

    def test_un_reaching_is_allowed_once_the_gate_is_reset(self) -> None:
        self.gate.action_reset()

        self.milestone.update_is_reached(False)

        self.assertFalse(self.milestone.is_reached)
        with self.assertRaises(ValidationError):
            self.gate.action_pass()

    def test_moving_the_milestone_of_a_gate_to_another_project_is_refused(
        self,
    ) -> None:
        with self.assertRaises(ValidationError):
            self.milestone.project_id = self.project_goats


@tagged("-at_install", "post_install")
class TestReviewPmChallengeRiskTask(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.risk = cls.env["project.risk"].create(
            {
                "name": "Supplier",
                "project_id": cls.project_pigs.id,
                "task_id": cls.task_1.id,
            }
        )

    def test_moving_a_risk_task_to_another_project_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            self.task_1.project_id = self.project_goats

        self.assertEqual(self.task_1.project_id, self.project_pigs)

    def test_a_task_without_risk_moves_freely(self) -> None:
        self.task_2.project_id = self.project_goats

        self.assertEqual(self.task_2.project_id, self.project_goats)

    def test_a_task_moves_once_its_risk_lets_go(self) -> None:
        self.risk.task_id = False

        self.task_1.project_id = self.project_goats

        self.assertEqual(self.task_1.project_id, self.project_goats)


@tagged("-at_install", "post_install")
class TestReviewPmChallengeResourceLoad(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.calendar_utc = cls.env["resource.calendar"].create(
            {"name": "Standard UTC", "tz": "UTC"}
        )
        cls.calendar_tokyo = cls.env["resource.calendar"].create(
            {"name": "Standard Tokyo", "tz": "Asia/Tokyo"}
        )

    def _make_resource(self, login: str, calendar):
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create({"name": login, "login": login})
        )
        resource = self.env["resource.resource"].create(
            {
                "name": login,
                "user_id": user.id,
                "calendar_id": calendar.id,
                "tz": calendar.tz,
            }
        )
        return user, resource

    def _reserve(self, resource, start, end, hours: float) -> None:
        task = self.env["project.task"].create(
            {"name": "load", "project_id": self.project_pigs.id}
        )
        reservation = self.env["resource.reservation"].create(
            {
                "name": task.name,
                "res_model": task._name,
                "res_id": task.id,
                "resource_id": resource.id,
                "date_start": start,
                "date_end": end,
                "enforcement_mode": "soft",
            }
        )
        reservation.allocated_hours = hours

    def _is_overallocated(self, user) -> bool:
        self.env.flush_all()
        self.env["project.resource.report"].invalidate_model()
        rows = self.env["project.resource.report"].search([("user_id", "=", user.id)])
        self.assertTrue(rows)
        return any(rows.mapped("is_overallocated"))

    def test_open_ended_and_zero_length_hours_load_their_start_week(self) -> None:
        for login, end in (
            ("open_ended_load", False),
            ("zero_length_load", datetime(2026, 9, 14, 8)),
        ):
            with self.subTest(login=login):
                user, resource = self._make_resource(login, self.calendar_utc)

                self._reserve(resource, datetime(2026, 9, 14, 8), end, 60)

                self.assertTrue(self._is_overallocated(user))

    def test_hours_follow_the_working_time_of_each_week(self) -> None:
        user, resource = self._make_resource("partial_days_load", self.calendar_utc)

        self._reserve(
            resource, datetime(2026, 9, 18, 16), datetime(2026, 9, 21, 10), 61
        )

        self.assertTrue(
            self._is_overallocated(user),
            "Friday 16:00-17:00 and Monday 08:00-10:00 split 61h as 20.3/40.7",
        )

    def test_weeks_are_read_in_the_zone_of_the_calendar(self) -> None:
        user, resource = self._make_resource("tokyo_load", self.calendar_tokyo)

        self._reserve(
            resource, datetime(2026, 9, 20, 23), datetime(2026, 9, 20, 23, 45), 30
        )
        self._reserve(resource, datetime(2026, 9, 16, 1), datetime(2026, 9, 16, 3), 30)

        self.assertFalse(
            self._is_overallocated(user),
            "Sunday 23:00 UTC is Monday 08:00 in Tokyo: two weeks of 30h",
        )


@tagged("post_install", "-at_install")
class TestReviewPmChallengeCrossCompanyReach(TestProjectCommon):
    def test_a_step_shared_with_another_companys_project_is_not_archived(
        self,
    ) -> None:
        other_company = self.env["res.company"].create({"name": "Elsewhere"})
        here = self.env["project.project"].create({"name": "Here"})
        there = self.env["project.project"].create(
            {"name": "There", "company_id": other_company.id}
        )
        step = self.env["project.workflow.step"].create(
            {"name": "Shared", "project_ids": [Command.set((here | there).ids)]}
        )
        stranded = self.env["project.task"].create(
            {"name": "theirs", "project_id": there.id, "step_id": step.id}
        )
        manager = self.user_projectmanager
        self.assertNotIn(other_company, manager.company_ids)
        with self.assertRaises(UserError):
            step.with_user(manager).action_archive()
        self.assertTrue(step.active)
        self.assertTrue(stranded.active)
