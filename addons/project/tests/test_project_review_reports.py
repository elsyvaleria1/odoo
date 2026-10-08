from datetime import date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from odoo import Command
from odoo.tests import freeze_time, tagged
from odoo.tools import get_lang

from .test_project_base import TestProjectCommon

STEP_HISTORY_REPORTS = ("project.task.burndown.chart.report", "project.cfd.report")


def _as_date(value):
    return value.date() if isinstance(value, datetime) else value


@tagged("post_install", "-at_install")
class TestStepHistoryReportTimezone(TestProjectCommon):
    INSTANTS = (
        datetime(2025, 3, 15, 12, 0),
        datetime(2025, 3, 1, 3, 0),
        datetime(2025, 2, 28, 20, 0),
        datetime(2025, 3, 2, 3, 0),
        datetime(2025, 3, 3, 3, 0),
    )
    TIMEZONES = (False, "America/Mexico_City", "Asia/Tokyo")

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.step = cls.env["project.workflow.step"].create({"name": "Only"})
        cls.projects = cls.env["project.project"].create(
            [
                {
                    "name": f"tz {instant}",
                    "workflow_step_ids": [Command.link(cls.step.id)],
                }
                for instant in cls.INSTANTS
            ]
        )
        tasks = cls.env["project.task"].create(
            [
                {"name": "t", "project_id": project.id, "step_id": cls.step.id}
                for project in cls.projects
            ]
        )
        cls.env.flush_all()
        for task, instant in zip(tasks, cls.INSTANTS, strict=True):
            cls.env.cr.execute(
                "UPDATE project_task SET create_date = %s WHERE id = %s",
                (instant, task.id),
            )
        cls.env.invalidate_all()

    def _expected_bucket(self, instant: datetime, tz: str | bool, interval: str):
        local = (
            instant.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(tz)).date()
            if tz
            else instant.date()
        )
        if interval == "month":
            return local.replace(day=1)
        week_start = int(get_lang(self.env).week_start)
        return local - timedelta(days=(local.isoweekday() - week_start) % 7)

    def _first_bucket(self, model: str, project, tz: str | bool, interval: str):
        rows = (
            self.env[model]
            .with_context(tz=tz)
            ._read_group(
                [("project_id", "=", project.id)],
                [f"date:{interval}", "step_id"],
                ["__count"],
            )
        )
        return min(_as_date(bucket) for bucket, _step, _count in rows)

    def test_a_task_first_appears_in_its_local_creation_bucket(self) -> None:
        for model in STEP_HISTORY_REPORTS:
            for interval in ("month", "week"):
                for tz in self.TIMEZONES:
                    for project, instant in zip(
                        self.projects, self.INSTANTS, strict=True
                    ):
                        with self.subTest(
                            model=model, interval=interval, tz=tz, instant=instant
                        ):
                            self.assertEqual(
                                self._first_bucket(model, project, tz, interval),
                                self._expected_bucket(instant, tz, interval),
                            )

    def test_buckets_are_contiguous_and_count_the_task_once(self) -> None:
        project = self.projects[0]
        for model in STEP_HISTORY_REPORTS:
            for tz in self.TIMEZONES:
                with self.subTest(model=model, tz=tz):
                    rows = (
                        self.env[model]
                        .with_context(tz=tz)
                        ._read_group(
                            [("project_id", "=", project.id)],
                            ["date:month", "step_id"],
                            ["__count"],
                        )
                    )
                    self.assertEqual({count for _d, _s, count in rows}, {1})
                    months = sorted(_as_date(d) for d, _s, _c in rows)
                    self.assertEqual(len(months), len(set(months)))
                    gaps = [
                        b
                        for a, b in pairwise(months)
                        if (b.year - a.year) * 12 + b.month - a.month != 1
                    ]
                    self.assertEqual(gaps, [])

    def test_burnup_closes_in_the_local_bucket_of_the_closure(self) -> None:
        project = self.projects[0]
        task = project.task_ids
        task.state = "done"
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE project_task SET date_closed = %s WHERE id = %s",
            (datetime(2025, 5, 1, 3, 0), task.id),
        )
        self.env.invalidate_all()
        report = self.env["project.task.burndown.chart.report"]
        for tz, closed_from in (
            (False, date(2025, 5, 1)),
            ("America/Mexico_City", date(2025, 4, 1)),
            ("Asia/Tokyo", date(2025, 5, 1)),
        ):
            with self.subTest(tz=tz):
                rows = report.with_context(tz=tz)._read_group(
                    [("project_id", "=", project.id)],
                    ["date:month", "is_closed"],
                    ["__count"],
                )
                closed = sorted(
                    _as_date(d) for d, state, _c in rows if state == "closed"
                )
                opened = sorted(_as_date(d) for d, state, _c in rows if state == "open")
                self.assertEqual(closed[0], closed_from)
                self.assertLess(opened[-1], closed_from)


@tagged("post_install", "-at_install")
class TestStepHistoryReportHistory(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "History"})
        cls.step_a, cls.step_b, cls.step_c, cls.step_d = cls.env[
            "project.workflow.step"
        ].create(
            [
                {
                    "name": name,
                    "sequence": seq,
                    "project_ids": [Command.link(cls.project.id)],
                }
                for seq, name in enumerate("ABCD", start=1)
            ]
        )

    def _create_task(self, name: str, step, when: str):
        with freeze_time(when):
            task = self.env["project.task"].create(
                {"name": name, "project_id": self.project.id, "step_id": step.id}
            )
            self.env.flush_all()
            self.env.cr.precommit.run()
        self.env.cr.execute(
            "UPDATE project_task SET create_date = %s WHERE id = %s",
            (datetime.fromisoformat(when), task.id),
        )
        self.env.invalidate_all()
        return task

    def _move(self, task, step, when: str) -> None:
        with freeze_time(when):
            task.step_id = step
            self.env.flush_all()
            self.env.cr.precommit.run()
        self.env.invalidate_all()

    def _per_month(self, model: str, tz: str | bool = False) -> dict:
        rows = (
            self.env[model]
            .with_context(tz=tz)
            ._read_group(
                [("project_id", "=", self.project.id)],
                ["date:month", "step_id"],
                ["__count"],
            )
        )
        return {
            (_as_date(bucket).isoformat()[:7], step.name or None): count
            for bucket, step, count in rows
        }

    def test_a_task_created_without_step_is_not_counted_twice(self) -> None:
        stepless = self._create_task(
            "stepless", self.env["project.workflow.step"], "2025-10-05 10:00:00"
        )
        self.assertFalse(stepless.step_id)
        stepped = self._create_task("stepped", self.step_a, "2025-10-05 10:00:00")
        self._move(stepless, self.step_b, "2025-10-20 10:00:00")
        self._move(stepped, self.step_b, "2025-10-20 10:00:00")

        for model in STEP_HISTORY_REPORTS:
            with self.subTest(model=model):
                per_month = self._per_month(model)
                self.assertEqual(per_month.get(("2025-10", "B")), 2)
                self.assertEqual(
                    {
                        key: count
                        for key, count in per_month.items()
                        if key[0] == "2025-10"
                    },
                    {("2025-10", "B"): 2},
                )
                self.assertEqual(per_month.get(("2025-11", "B")), 2)

    def test_the_step_of_a_bucket_is_the_step_held_at_its_end(self) -> None:
        task = self._create_task("busy", self.step_a, "2025-01-10 10:00:00")
        self._move(task, self.step_b, "2025-03-05 10:00:00")
        self._move(task, self.step_c, "2025-03-12 10:00:00")
        self._move(task, self.step_d, "2025-03-20 10:00:00")

        for model in STEP_HISTORY_REPORTS:
            with self.subTest(model=model):
                per_month = self._per_month(model)
                self.assertEqual(per_month.get(("2025-02", "A")), 1)
                self.assertEqual(
                    {k: c for k, c in per_month.items() if k[0] == "2025-03"},
                    {("2025-03", "D"): 1},
                )
                self.assertEqual(
                    {k: c for k, c in per_month.items() if k[0] == "2025-04"},
                    {("2025-04", "D"): 1},
                )

    def test_cfd_and_burndown_agree(self) -> None:
        task = self._create_task("agree", self.step_a, "2025-01-10 10:00:00")
        self._move(task, self.step_b, "2025-04-05 10:00:00")
        self._create_task("other", self.step_c, "2025-02-10 10:00:00")
        for tz in (False, "America/Mexico_City"):
            with self.subTest(tz=tz):
                self.assertEqual(
                    self._per_month("project.cfd.report", tz),
                    self._per_month("project.task.burndown.chart.report", tz),
                )


@tagged("post_install", "-at_install")
class TestTaskAnalysisReport(TestProjectCommon):
    def test_archived_tasks_are_hidden_by_default(self) -> None:
        archived = self.env["project.task"].create(
            {"name": "archived", "project_id": self.project_pigs.id}
        )
        archived.active = False
        self.env.flush_all()
        report = self.env["report.project.task.user"]
        self.assertFalse(report.search([("task_id", "=", archived.id)]))
        self.assertEqual(
            len(
                report.with_context(active_test=False).search(
                    [("task_id", "=", archived.id)]
                )
            ),
            1,
        )

    def test_a_task_rated_several_times_is_one_row(self) -> None:
        task = self.task_1
        rating_vals = {
            "res_model_id": self.env["ir.model"]._get("project.task").id,
            "res_id": task.id,
            "rated_partner_id": self.partner_1.id,
            "partner_id": self.partner_1.id,
            "consumed": True,
        }
        self.env["rating.rating"].create(
            [{**rating_vals, "rating": 5}, {**rating_vals, "rating": 3}]
        )
        self.env.flush_all()
        rows = self.env["report.project.task.user"].search([("task_id", "=", task.id)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.rating_avg, 4)


@tagged("post_install", "-at_install")
class TestResourceReportLoad(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.calendar = cls.env["resource.calendar"].create(
            {"name": "Standard UTC", "tz": "UTC"}
        )
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create({"name": "Loaded", "login": "loaded_resource_report"})
        )
        cls.resource = cls.env["resource.resource"].create(
            {
                "name": "Loaded",
                "user_id": cls.user.id,
                "calendar_id": cls.calendar.id,
                "tz": "UTC",
            }
        )

    def _reserve(self, start: datetime, end: datetime, **vals):
        task = self.env["project.task"].create(
            {"name": "load", "project_id": self.project_pigs.id}
        )
        return self.env["resource.reservation"].create(
            {
                "name": task.name,
                "res_model": task._name,
                "res_id": task.id,
                "resource_id": self.resource.id,
                "date_start": start,
                "date_end": end,
                **vals,
            }
        )

    def _is_overallocated(self) -> bool:
        self.env.flush_all()
        rows = self.env["project.resource.report"].search(
            [("user_id", "=", self.user.id)]
        )
        self.assertTrue(rows)
        return any(rows.mapped("is_overallocated"))

    def test_a_reservation_spanning_two_weeks_is_split_across_them(self) -> None:
        reservation = self._reserve(
            datetime(2025, 3, 3, 8, 0), datetime(2025, 3, 14, 17, 0)
        )
        self.assertEqual(reservation.allocated_hours, 80)
        self.assertFalse(self._is_overallocated())

    def test_an_archived_reservation_is_not_load(self) -> None:
        self._reserve(datetime(2025, 3, 3, 8, 0), datetime(2025, 3, 7, 17, 0))
        archived = self._reserve(
            datetime(2025, 3, 4, 8, 0), datetime(2025, 3, 4, 17, 0)
        )
        archived.active = False
        self.assertFalse(self._is_overallocated())

    def test_a_week_over_capacity_is_overallocated(self) -> None:
        self._reserve(datetime(2025, 3, 3, 8, 0), datetime(2025, 3, 7, 17, 0))
        self._reserve(datetime(2025, 3, 4, 8, 0), datetime(2025, 3, 4, 17, 0))
        self.assertTrue(self._is_overallocated())
