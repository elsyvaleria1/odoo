import random
from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import freeze_time, tagged

from odoo.addons.project.tests.test_project_base import TestProjectCommon


@tagged("-at_install", "post_install")
class TestReviewPmUpdate(TestProjectCommon):
    def test_project_user_deletes_own_update(self) -> None:
        Update = self.env["project.update"].with_user(self.user_projectuser)
        update = Update.create(
            {"name": "Mine", "project_id": self.project_pigs.id, "status": "on_track"}
        )
        self.assertEqual(self.project_pigs.last_update_id, update)
        update.unlink()
        self.assertFalse(self.project_pigs.last_update_id)

    def test_last_update_is_latest_by_date_on_every_path(self) -> None:
        today = fields.Date.today()
        Update = self.env["project.update"]
        recent = Update.create(
            {
                "name": "Recent",
                "project_id": self.project_pigs.id,
                "status": "on_track",
                "date": today,
            }
        )
        backdated = Update.create(
            {
                "name": "Backdated",
                "project_id": self.project_pigs.id,
                "status": "at_risk",
                "date": today - timedelta(days=3),
            }
        )
        self.assertEqual(
            self.project_pigs.last_update_id,
            recent,
            "create must agree with unlink: the latest update is the newest date",
        )
        backdated.date = today + timedelta(days=1)
        self.assertEqual(self.project_pigs.last_update_id, backdated)
        backdated.unlink()
        self.assertEqual(self.project_pigs.last_update_id, recent)


@tagged("-at_install", "post_install")
class TestReviewPmSprint(TestProjectCommon):
    def _make_sprint(self, state="planning"):
        today = fields.Date.today()
        return self.env["project.sprint"].create(
            {
                "name": "S",
                "project_id": self.project_pigs.id,
                "date_start": today,
                "date_end": today + timedelta(days=14),
                "state": state,
            }
        )

    def _make_task(self, state, hours=1.0):
        return self.env["project.task"].create(
            {
                "name": state,
                "project_id": self.project_pigs.id,
                "state": state,
                "planned_hours": hours,
            }
        )

    def test_sprint_goes_through_review_and_closes(self) -> None:
        sprint = self._make_sprint()
        sprint.action_start()
        sprint.action_review()
        self.assertEqual(sprint.state, "review")
        sprint.action_close()
        self.assertEqual(sprint.state, "closed")

    def test_closed_sprint_cannot_restart_or_reclose(self) -> None:
        sprint = self._make_sprint(state="active")
        sprint.task_ids = self._make_task("in_progress", hours=3.0)
        sprint.action_close()
        self.assertEqual(sprint.carried_over_count, 1)
        with self.assertRaises(UserError):
            sprint.action_start()
        with self.assertRaises(UserError):
            sprint.action_close()
        self.assertEqual(sprint.state, "closed")
        self.assertEqual(sprint.carried_over_count, 1)
        self.assertEqual(sprint.carried_over_hours, 3.0)

    def test_review_needs_an_active_sprint(self) -> None:
        with self.assertRaises(UserError):
            self._make_sprint().action_review()

    def test_cancelled_tasks_are_not_velocity(self) -> None:
        sprint = self._make_sprint()
        sprint.task_ids = self._make_task("done", hours=6.0) | self._make_task(
            "canceled", hours=5.0
        )
        self.assertEqual(sprint.completed_count, 1)
        self.assertEqual(sprint.velocity, 6.0)
        self.assertEqual(sprint.completion_pct, 50.0)


@tagged("-at_install", "post_install")
class TestReviewPmHistory(TestProjectCommon):
    def test_snapshot_is_idempotent_per_day(self) -> None:
        History = self.env["project.history"]
        first = History.create_from_project(self.project_pigs)
        self.env["project.task"].create(
            {"name": "Later", "project_id": self.project_pigs.id}
        )
        second = History.create_from_project(self.project_pigs)
        self.assertEqual(first, second)
        self.assertEqual(
            History.search_count([("project_id", "=", self.project_pigs.id)]), 1
        )
        self.assertEqual(second.task_count, 3)

    def test_snapshot_keeps_company_after_project_is_deleted(self) -> None:
        project = self.env["project.project"].create({"name": "Gone"})
        history = self.env["project.history"].create_from_project(project)
        self.assertEqual(history.company_id, project.company_id)
        company = project.company_id
        project.unlink()
        self.assertFalse(history.project_id)
        self.assertEqual(history.company_id, company)

    def test_snapshot_measures(self) -> None:
        now = fields.Datetime.now()
        project = self.env["project.project"].create({"name": "Measured"})
        Task = self.env["project.task"]
        met, missed, open_task = Task.create(
            [
                {
                    "name": "met",
                    "project_id": project.id,
                    "date_end": now + timedelta(days=5),
                    "planned_hours": 4.0,
                    "user_ids": self.user_projectuser.ids,
                },
                {
                    "name": "missed",
                    "project_id": project.id,
                    "date_end": now - timedelta(days=5),
                    "planned_hours": 6.0,
                    "user_ids": (self.user_projectuser | self.user_projectmanager).ids,
                },
                {"name": "open", "project_id": project.id, "planned_hours": 1.0},
            ]
        )
        (met | missed).write({"state": "done"})
        history = self.env["project.history"].create_from_project(project)
        self.assertEqual(history.task_count, 3)
        self.assertEqual(history.team_size, len((met | missed | open_task).user_ids))
        self.assertEqual(history.planned_hours, 11.0)
        self.assertEqual(history.deadline_compliance_pct, 50.0)
        self.assertEqual(history.date_completed, fields.Date.today())


@tagged("-at_install", "post_install")
class TestReviewPmColumns(TestProjectCommon):
    def test_copy_honours_default_name(self) -> None:
        phase = self.env["project.phase"].create({"name": "Planning"})
        step = self.env["project.workflow.step"].create({"name": "Backlog"})
        triage = self.env["project.triage"].create(
            {"name": "Today", "user_id": self.user_projectuser.id}
        )
        self.assertEqual(phase.copy({"name": "Execution"}).name, "Execution")
        self.assertEqual(step.copy({"name": "Ready"}).name, "Ready")
        self.assertEqual(triage.copy({"name": "Later"}).name, "Later")
        self.assertEqual(phase.copy().name, "Planning (copy)")

    def test_phase_unarchive_restores_only_what_it_archived(self) -> None:
        self.user_projectmanager.group_ids += self.env.ref(
            "project.group_project_stages"
        )
        phase = self.env["project.phase"].create({"name": "Closing"})
        Project = self.env["project.project"]
        cascaded = Project.create({"name": "Cascaded", "phase_id": phase.id})
        shelved = Project.create({"name": "Shelved", "phase_id": phase.id})
        shelved.active = False
        wizard = (
            self.env["wizard.project.phase.delete"]
            .with_user(self.user_projectmanager)
            .create({"phase_ids": phase.ids})
        )
        self.assertEqual(wizard.projects_count, 2)
        wizard.action_archive()
        self.assertFalse(phase.active)
        self.assertFalse(cascaded.active)
        phase.action_unarchive()
        self.assertTrue(cascaded.active, "the cascade is undone with the phase")
        self.assertFalse(shelved.active, "a project archived on its own stays so")
        phase.action_archive()
        phase.action_unarchive()
        self.assertTrue(cascaded.active)

    def test_step_unarchive_restores_only_what_it_archived(self) -> None:
        step = self.project_goats.workflow_step_ids[0]
        Task = self.env["project.task"]
        cascaded = Task.create(
            {
                "name": "Cascaded",
                "project_id": self.project_goats.id,
                "step_id": step.id,
            }
        )
        shelved = Task.create(
            {"name": "Shelved", "project_id": self.project_goats.id, "step_id": step.id}
        )
        shelved.active = False
        wizard = (
            self.env["wizard.project.workflow.step.delete"]
            .with_user(self.user_projectmanager)
            .create({"step_ids": step.ids, "project_ids": self.project_goats.ids})
        )
        self.assertEqual(wizard.tasks_count, 2)
        wizard.action_archive()
        self.assertFalse(step.active)
        self.assertFalse(cascaded.active)
        step.action_unarchive()
        self.assertTrue(cascaded.active)
        self.assertFalse(shelved.active)


@tagged("-at_install", "post_install")
class TestReviewPmGate(TestProjectCommon):
    def setUp(self) -> None:
        super().setUp()
        self.project_pigs.allow_milestones = True
        self.milestone = self.env["project.milestone"].create(
            {"name": "M", "project_id": self.project_pigs.id}
        )
        self.gate = self.env["project.gate"].create(
            {
                "name": "G",
                "project_id": self.project_pigs.id,
                "milestone_id": self.milestone.id,
                "criterion_ids": [
                    fields.Command.create({"name": "Budget"}),
                    fields.Command.create({"name": "Scope"}),
                ],
            }
        )

    def test_gate_passes_only_with_every_criterion_met(self) -> None:
        self.milestone.is_reached = True
        with self.assertRaises(ValidationError):
            self.gate.action_pass()
        with self.assertRaises(ValidationError):
            self.gate.state = "passed"
        self.gate.criterion_ids.is_met = True
        self.gate.action_pass()
        self.assertEqual(self.gate.state, "passed")
        self.assertEqual(self.gate.date_review, fields.Date.context_today(self.gate))
        with self.assertRaises(ValidationError):
            self.gate.criterion_ids[0].is_met = False

    def test_gate_waits_for_its_milestone(self) -> None:
        self.gate.criterion_ids.is_met = True
        with self.assertRaises(ValidationError):
            self.gate.action_pass()
        self.milestone.is_reached = True
        self.gate.action_pass()
        self.assertEqual(self.gate.state, "passed")

    def test_gate_fail_defer_and_reset(self) -> None:
        self.gate.action_fail()
        self.assertEqual(self.gate.state, "failed")
        self.gate.action_reset()
        self.assertEqual(self.gate.state, "pending")
        self.gate.action_defer()
        self.assertEqual(self.gate.state, "deferred")


@tagged("-at_install", "post_install")
class TestReviewPmBaseline(TestProjectCommon):
    def test_baseline_line_variance_and_frozen_snapshot(self) -> None:
        start = fields.Datetime.now().replace(microsecond=0)
        task = self.env["project.task"].create(
            {
                "name": "Planned",
                "project_id": self.project_goats.id,
                "date_start": start,
                "date_end": start + timedelta(days=2),
                "planned_hours": 8.0,
            }
        )
        baseline = self.env["project.baseline"].create(
            {"name": "Plan", "project_id": self.project_goats.id}
        )
        baseline.action_capture_snapshot()
        line = baseline.line_ids.filtered(lambda ln: ln.task_id == task)
        self.assertEqual(line.hours_variance, 0.0)
        task.write(
            {
                "date_start": start + timedelta(days=1),
                "date_end": start + timedelta(days=5),
                "planned_hours": 10.0,
            }
        )
        self.assertEqual(line.start_variance_days, 1.0)
        self.assertEqual(line.end_variance_days, 3.0)
        self.assertEqual(line.hours_variance, 2.0)
        with self.assertRaises(UserError):
            line.planned_hours = 99.0
        line.sequence = 3


@tagged("-at_install", "post_install")
class TestReviewPmRatingSchedule(TestProjectCommon):
    def test_rating_period_change_reschedules(self) -> None:
        step = self.env["project.workflow.step"].create(
            {
                "name": "Rated",
                "rating_active": True,
                "rating_status": "periodic",
                "rating_status_period": "monthly",
            }
        )
        now = fields.Datetime.now()
        self.assertGreater(step.date_rating_request, now + timedelta(days=29))
        step.rating_status_period = "daily"
        self.assertLess(step.date_rating_request, now + timedelta(days=2))
        step.rating_active = False
        self.assertFalse(step.date_rating_request)


@tagged("-at_install", "post_install")
class TestReviewPmForecast(TestProjectCommon):
    @freeze_time("2027-03-17 12:00:00")
    def test_throughput_uses_complete_local_weeks(self) -> None:
        project = self.env["project.project"].create({"name": "Forecast"})
        tasks = self.env["project.task"].create(
            [
                {"name": f"T{i}", "project_id": project.id, "state": "done"}
                for i in range(3)
            ]
        )
        tasks[0].date_closed = datetime(2027, 3, 10, 12, 0)
        tasks[1].date_closed = datetime(2027, 3, 15, 3, 0)
        tasks[2].date_closed = datetime(2027, 3, 16, 9, 0)
        wizard = (
            self.env["wizard.project.project.view.forecast"]
            .with_context(tz="America/Mexico_City")
            .create({"project_id": project.id, "weeks_of_history": 4})
        )
        throughput = wizard._get_weekly_throughput()
        self.assertEqual(
            throughput[-1],
            2,
            "Monday 03:00 UTC is Sunday in Mexico City: last week's, and the "
            "current partial week is left out",
        )
        self.assertEqual(sum(throughput), 2)

    def test_simulation_is_seedable_and_capped(self) -> None:
        Wizard = self.env["wizard.project.project.view.forecast"]
        first = Wizard._get_simulated_weeks([0, 1, 3], 10, 500, random.Random(7))
        second = Wizard._get_simulated_weeks([0, 1, 3], 10, 500, random.Random(7))
        self.assertEqual(first, second)
        wizard = Wizard.create(
            {
                "project_id": self.project_pigs.id,
                "simulation_count": Wizard.SIMULATION_COUNT_MAX + 1,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_run_forecast()


@tagged("-at_install", "post_install")
class TestReviewPmRetrospectiveRisk(TestProjectCommon):
    def test_carry_forward_closes_the_originals(self) -> None:
        Retro = self.env["project.retrospective"]
        previous = Retro.create({"name": "R1", "project_id": self.project_pigs.id})
        action = self.env["project.retrospective.action"].create(
            {
                "name": "Fix CI",
                "retrospective_id": previous.id,
                "owner_id": self.user_projectuser.id,
            }
        )
        current = Retro.create(
            {
                "name": "R2",
                "project_id": self.project_pigs.id,
                "previous_id": previous.id,
            }
        )
        current.action_carry_forward()
        self.assertEqual(action.state, "carried")
        self.assertEqual(previous.open_action_count, 0)
        self.assertEqual(current.open_action_count, 1)
        self.assertEqual(current.action_ids.carried_from_id, action)

    def test_previous_retrospective_belongs_to_the_project(self) -> None:
        Retro = self.env["project.retrospective"]
        other = Retro.create({"name": "Other", "project_id": self.project_goats.id})
        with self.assertRaises(ValidationError):
            Retro.create(
                {
                    "name": "Mine",
                    "project_id": self.project_pigs.id,
                    "previous_id": other.id,
                }
            )

    def test_risk_task_belongs_to_the_project(self) -> None:
        goat_task = self.env["project.task"].create(
            {"name": "Goat", "project_id": self.project_goats.id}
        )
        with self.assertRaises(ValidationError):
            self.env["project.risk"].create(
                {
                    "name": "Cross",
                    "project_id": self.project_pigs.id,
                    "task_id": goat_task.id,
                }
            )

    def test_resolving_a_risk_dates_it(self) -> None:
        risk = self.env["project.risk"].create(
            {"name": "R", "project_id": self.project_pigs.id}
        )
        risk.state = "resolved"
        self.assertEqual(risk.date_resolved, fields.Date.context_today(risk))


@tagged("-at_install", "post_install")
class TestReviewPmMilestone(TestProjectCommon):
    def test_done_count_follows_task_state(self) -> None:
        self.project_pigs.allow_milestones = True
        milestone = self.env["project.milestone"].create(
            {"name": "M", "project_id": self.project_pigs.id}
        )
        self.task_1.milestone_id = milestone
        self.assertEqual((milestone.task_count, milestone.done_task_count), (1, 0))
        self.task_1.state = "done"
        self.assertEqual((milestone.task_count, milestone.done_task_count), (1, 1))
        self.assertTrue(milestone.can_be_marked_as_done)
        self.project_pigs.allow_milestones = False
        milestone.invalidate_recordset()
        self.assertEqual(milestone.task_count, 0)
        self.assertFalse(milestone.can_be_marked_as_done)
