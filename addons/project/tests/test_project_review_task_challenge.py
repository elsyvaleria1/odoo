from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import Form, HttpCase, tagged
from odoo.tests.common import new_test_user

from .test_project_base import TestProjectCommon


class TestRecurrenceAfterItsEnd(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref("project.group_project_recurring_tasks")
        cls.project_pigs.allow_recurring_tasks = True

    def _series(self, **vals):
        return self.env["project.task"].create(
            {
                "name": "r",
                "project_id": self.project_pigs.id,
                "recurring_task": True,
                "repeat_interval": 1,
                "repeat_unit": "week",
                **vals,
            }
        )

    def test_closing_an_overdue_occurrence_of_an_ended_series(self) -> None:
        until = fields.Date.today() + timedelta(days=10)
        task = self._series(
            repeat_type="until",
            repeat_until=until,
            date_start=datetime.combine(until, datetime.min.time())
            - timedelta(days=60),
            date_end=datetime.combine(until, datetime.min.time()) - timedelta(days=59),
        )
        recurrences_before = self.env["project.task.recurrence"].search_count([])
        with freeze_time(until + timedelta(days=30)):
            task.state = "done"
        self.assertEqual(task.state, "done")
        self.assertEqual(len(task.recurrence_id.task_ids), 2)
        self.assertEqual(
            self.env["project.task.recurrence"].search_count([]), recurrences_before
        )

    def test_a_new_occurrence_leaves_no_orphan_recurrence(self) -> None:
        task = self._series(repeat_type="forever")
        before = self.env["project.task.recurrence"].search_count([])
        task.state = "done"
        self.assertEqual(len(task.recurrence_id.task_ids), 2)
        self.assertEqual(self.env["project.task.recurrence"].search_count([]), before)

    def test_ending_a_series_clears_its_archived_occurrences(self) -> None:
        first = self._series(repeat_type="forever")
        first.state = "done"
        second = first.recurrence_id.task_ids - first
        first.active = False
        second.recurring_task = False
        self.assertFalse(first.recurring_task)


class TestTaskSearchEdges(TestProjectCommon):
    def test_effective_start_in_a_mixed_list_keeps_undated_tasks(self) -> None:
        date = datetime(2026, 1, 10, 10, 0)
        undated, dated, other = self.env["project.task"].create(
            [
                {"name": "u", "project_id": self.project_pigs.id},
                {"name": "d", "project_id": self.project_pigs.id, "date_end": date},
                {
                    "name": "o",
                    "project_id": self.project_pigs.id,
                    "date_end": date + timedelta(days=1),
                },
            ]
        )
        tasks = undated | dated | other

        def search(domain):
            return self.env["project.task"].search([("id", "in", tasks.ids), domain])

        self.assertEqual(
            search(("date_start_effective", "in", [False, date])), undated | dated
        )
        self.assertEqual(search(("date_start_effective", "!=", date)), undated | other)
        self.assertEqual(
            search(("date_start_effective", "not in", [date])), undated | other
        )

    def test_comodel_search_with_ids_and_names(self) -> None:
        users = self.env["project.task"]._search_on_comodel(
            [("user_ids", "in", ["Armande ProjectUser", self.user_projectmanager.id])],
            "user_ids",
            "res.users",
        )
        self.assertEqual(users, self.user_projectuser | self.user_projectmanager)


class TestDependencyWarningEdges(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.project_pigs.allow_dependencies = True
        cls.predecessor = cls.env["project.task"].create(
            {
                "name": "pred",
                "project_id": cls.project_pigs.id,
                "date_start": "2026-01-01 08:00:00",
                "date_end": "2026-01-10 18:00:00",
            }
        )
        cls.task = cls.env["project.task"].create(
            {
                "name": "task",
                "project_id": cls.project_pigs.id,
                "date_start": "2026-01-05 08:00:00",
                "date_end": "2026-01-06 18:00:00",
                "predecessor_ids": [Command.link(cls.predecessor.id)],
            }
        )

    def test_turning_dependencies_off_clears_the_warning(self) -> None:
        self.assertTrue(self.task.dependency_warning)
        self.project_pigs.allow_dependencies = False
        self.assertFalse(self.task.dependency_warning)

    def test_compute_and_search_agree_for_a_user_who_cannot_read_the_predecessor(
        self,
    ) -> None:
        self.predecessor.project_id = self.project_goats
        user = new_test_user(
            self.env, "dep_reader", groups="project.group_project_user"
        )
        self.project_pigs.privacy_visibility = "employees"
        Task = self.env["project.task"].with_user(user)
        self.assertFalse(self.predecessor.with_user(user).has_access("read"))
        task = Task.browse(self.task.id)
        self.assertTrue(task.dependency_warning)
        self.assertNotIn("pred", task.dependency_warning)
        self.assertIn(task, Task.search([("dependency_warning", "!=", False)]))


class TestScheduledHoursWindows(TestProjectCommon):
    def test_far_apart_tasks_are_fetched_in_separate_windows(self) -> None:
        tasks = self.env["project.task"].create(
            [
                {
                    "name": "now",
                    "project_id": self.project_pigs.id,
                    "date_start": "2026-03-02 08:00:00",
                    "date_end": "2026-03-04 17:00:00",
                },
                {
                    "name": "soon",
                    "project_id": self.project_pigs.id,
                    "date_start": "2026-03-05 08:00:00",
                    "date_end": "2026-03-06 17:00:00",
                },
                {
                    "name": "typo",
                    "project_id": self.project_pigs.id,
                    "date_start": "1026-03-02 08:00:00",
                    "date_end": "1026-03-04 17:00:00",
                },
            ]
        )
        windows = tasks._split_scheduling_windows()
        self.assertEqual(len(windows), 2)
        for task in tasks:
            self.assertAlmostEqual(
                task.scheduled_hours,
                round(
                    task._scheduling_get_work_hours(
                        task.date_start, task.date_end, compute_leaves=True
                    ),
                    2,
                ),
            )


class TestSubtaskCreationFromAParent(TestProjectCommon):
    def test_a_form_with_only_a_parent_gets_the_parents_project_step(self) -> None:
        parent = self.env["project.task"].create(
            {"name": "P", "project_id": self.project_pigs.id}
        )
        with Form(
            self.env["project.task"].with_context(default_parent_id=parent.id)
        ) as form:
            form.name = "child"
        child = form.record
        self.assertEqual(child.project_id, self.project_pigs)
        self.assertTrue(child.step_id)
        self.assertIn(self.project_pigs, child.step_id.project_ids)

    def test_a_subtask_carried_by_its_parent_takes_the_new_steps_state(self) -> None:
        target = self.env["project.project"].create({"name": "Target"})
        self.env["project.workflow.step"].create(
            {
                "name": "Doing",
                "sequence": 0,
                "task_state": "in_progress",
                "project_ids": [Command.link(target.id)],
            }
        )
        parent = self.env["project.task"].create(
            {"name": "P", "project_id": self.project_pigs.id}
        )
        child = self.env["project.task"].create({"name": "c", "parent_id": parent.id})
        child.state = "approved"
        parent.project_id = target
        self.assertEqual(child.project_id, target)
        self.assertEqual(child.state, "in_progress")

    def test_a_creator_following_parent_and_project_keeps_the_parents_subtypes(
        self,
    ) -> None:
        note = self.env.ref("mail.mt_note")
        creator = self.user_projectmanager
        self.project_pigs.message_subscribe(creator.partner_id.ids)
        parent = self.env["project.task"].create(
            {"name": "P", "project_id": self.project_pigs.id}
        )
        parent.message_subscribe(creator.partner_id.ids, note.ids)
        child = (
            self.env["project.task"]
            .with_user(creator)
            .create({"name": "c", "parent_id": parent.id})
        )
        follower = child.message_follower_ids.filtered(
            lambda f: f.partner_id == creator.partner_id
        )
        self.assertEqual(follower.subtype_ids, note)

    def test_every_internal_partner_sharing_a_cc_address_follows(self) -> None:
        twins = self.env["res.partner"].create(
            [
                {"name": "Twin A", "email": "twin@example.com"},
                {"name": "Twin B", "email": "Twin@Example.com"},
            ]
        )
        for twin, email in zip(
            twins, ("twin@example.com", "Twin@Example.com"), strict=True
        ):
            new_test_user(
                self.env,
                f"twin_{twin.id}",
                groups="base.group_user",
                partner_id=twin.id,
            )
            twin.email = email
        task = self.env["project.task"].create(
            {
                "name": "cc",
                "project_id": self.project_pigs.id,
                "email_cc": "twin@example.com",
            }
        )
        self.assertTrue(twins <= task.message_partner_ids)


@tagged("post_install", "-at_install")
class TestPortalMailViewLink(HttpCase):
    def test_a_portal_customer_opens_the_task_from_the_email_link(self) -> None:
        customer = new_test_user(
            self.env, "mailview_customer", groups="base.group_portal"
        )
        project = self.env["project.project"].create(
            {
                "name": "Shared",
                "privacy_visibility": "portal",
                "partner_id": customer.partner_id.id,
            }
        )
        task = self.env["project.task"].create(
            {
                "name": "Seen by the customer",
                "project_id": project.id,
                "partner_id": customer.partner_id.id,
            }
        )
        task.message_subscribe(customer.partner_id.ids)
        self.authenticate("mailview_customer", "mailview_customer")
        response = self.url_open(
            f"/mail/view?model=project.task&res_id={task.id}", allow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Seen by the customer", response.text)
        self.assertNotIn("access_token", response.url)
