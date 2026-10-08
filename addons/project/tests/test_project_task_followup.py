from datetime import datetime

from markupsafe import Markup

from odoo import Command
from odoo.db.metrics import observing_statements
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import freeze_time, tagged

from .test_project_base import TestProjectCommon


@tagged("post_install", "-at_install")
class TestFirstAssignment(TestProjectCommon):
    def test_the_first_assignment_is_written_once(self) -> None:
        with freeze_time("2100-01-04 08:00:00"):
            task = self.env["project.task"].create(
                {
                    "name": "Queued",
                    "project_id": self.project_pigs.id,
                    "user_ids": [Command.clear()],
                }
            )
        self.assertFalse(task.date_first_assign)
        with freeze_time("2100-01-04 10:00:00"):
            task.user_ids = self.user_projectuser
        first = datetime(2100, 1, 4, 10)
        self.assertEqual((task.date_assign, task.date_first_assign), (first, first))
        with freeze_time("2100-01-05 10:00:00"):
            task.user_ids = False
        self.assertFalse(task.date_assign)
        self.assertEqual(task.date_first_assign, first)
        with freeze_time("2100-01-06 10:00:00"):
            task.user_ids = self.user_projectmanager
        self.assertEqual(task.date_assign, datetime(2100, 1, 6, 10))
        self.assertEqual(task.date_first_assign, first)

    def test_a_task_created_assigned_stamps_both(self) -> None:
        with freeze_time("2100-01-04 08:00:00"):
            task = self.env["project.task"].create(
                {
                    "name": "Assigned",
                    "project_id": self.project_pigs.id,
                    "user_ids": [Command.set(self.user_projectuser.ids)],
                }
            )
        self.assertEqual(task.date_first_assign, datetime(2100, 1, 4, 8))
        self.assertEqual(task.date_first_assign, task.date_assign)

    def test_a_default_assignee_is_a_first_assignment(self) -> None:
        task = self.env["project.task"].create({"name": "Private"})
        self.assertEqual(task.user_ids, self.env.user)
        self.assertFalse(task.date_assign)
        self.assertEqual(task.date_first_assign, task.create_date)

    def test_queue_and_cycle_time_read_the_first_assignment(self) -> None:
        project = self.env["project.project"].create({"name": "No calendar"})
        (project.company_id | self.env.company).resource_calendar_id = False
        project.invalidate_recordset(["resource_calendar_id"])
        task = self.env["project.task"].create({"name": "t", "project_id": project.id})
        task.state = "done"
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE project_task SET create_date = %s, date_first_assign = %s, "
            "date_assign = %s, date_closed = %s WHERE id = %s",
            (
                "2100-01-04 08:00:00",
                "2100-01-04 12:00:00",
                "2100-01-04 20:00:00",
                "2100-01-05 08:00:00",
                task.id,
            ),
        )
        self.env.invalidate_all()
        task.modified(["create_date", "date_first_assign", "date_closed"])
        self.env.flush_all()
        self.assertEqual(task.queue_time_hours, 4.0)
        self.assertEqual(task.cycle_time_hours, 20.0)


@tagged("post_install", "-at_install")
@freeze_time("2100-01-04")
class TestPlanningOverlapInMemory(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        (cls.task_1 | cls.task_2).write({"user_ids": cls.user_projectuser.ids})
        cls.task_1.write(
            {
                "date_start": datetime(2100, 1, 4, 8),
                "date_end": datetime(2100, 1, 4, 10),
                "planned_hours": 2,
            }
        )
        cls.warning = Markup("<p>Armande ProjectUser has 1 tasks at the same time.</p>")

    def test_moving_out_of_an_overlap_clears_the_warning(self) -> None:
        self.task_2.write(
            {
                "date_start": datetime(2100, 1, 4, 9),
                "date_end": datetime(2100, 1, 4, 11),
                "planned_hours": 2,
            }
        )
        self.assertEqual(self.task_1.planning_overlap, self.warning)
        edited = self.task_1.new(
            {
                "date_start": datetime(2100, 1, 5, 8),
                "date_end": datetime(2100, 1, 5, 10),
            },
            origin=self.task_1,
        )
        self.assertFalse(edited.planning_overlap)
        self.assertEqual(self.task_1.planning_overlap, self.warning)

    def test_moving_into_an_overlap_shows_the_warning(self) -> None:
        self.task_2.write(
            {
                "date_start": datetime(2100, 1, 5, 9),
                "date_end": datetime(2100, 1, 5, 11),
                "planned_hours": 2,
            }
        )
        self.assertFalse(self.task_1.planning_overlap)
        edited = self.task_1.new(
            {
                "date_start": datetime(2100, 1, 5, 8),
                "date_end": datetime(2100, 1, 5, 10),
            },
            origin=self.task_1,
        )
        self.assertEqual(edited.planning_overlap, self.warning)

    def test_a_new_record_sees_the_overlap(self) -> None:
        draft = self.env["project.task"].new(
            {
                "name": "Draft",
                "project_id": self.project_pigs.id,
                "user_ids": self.user_projectuser.ids,
                "date_start": datetime(2100, 1, 4, 9),
                "date_end": datetime(2100, 1, 4, 11),
                "planned_hours": 2,
            }
        )
        self.assertEqual(draft.planning_overlap, self.warning)

    def test_an_unassigned_edit_drops_the_warning(self) -> None:
        self.task_2.write(
            {
                "date_start": datetime(2100, 1, 4, 9),
                "date_end": datetime(2100, 1, 4, 11),
                "planned_hours": 2,
            }
        )
        edited = self.task_1.new({"user_ids": [Command.clear()]}, origin=self.task_1)
        self.assertFalse(edited.planning_overlap)


@tagged("post_install", "-at_install")
class TestScheduledHoursCalendar(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company_b = cls.env["res.company"].create({"name": "No calendar"})
        cls.company_b.resource_calendar_id = False
        cls.user_b = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "B user",
                    "login": "b_user_scheduled",
                    "company_id": cls.company_b.id,
                    "company_ids": [Command.set(cls.company_b.ids)],
                    "group_ids": [
                        Command.set(
                            [
                                cls.env.ref("base.group_user").id,
                                cls.env.ref("project.group_project_user").id,
                            ]
                        )
                    ],
                }
            )
        )
        cls.monday = datetime(2100, 1, 4)
        cls.tuesday = datetime(2100, 1, 5)

    def _private_task(self, users, env=None):
        env = env or self.env
        return (
            env["project.task"]
            .with_context(default_user_ids=users.ids)
            .create(
                {
                    "name": "Private",
                    "date_start": self.monday,
                    "date_end": self.tuesday,
                    "user_ids": [Command.set(users.ids)],
                }
            )
        )

    def test_the_company_calendar_of_a_unique_assignee_company(self) -> None:
        calendar = self.env.company.resource_calendar_id
        expected = calendar.get_work_hours_count(self.monday, self.tuesday)
        task = self._private_task(self.user_projectuser)
        self.assertFalse(task.company_id)
        self.assertEqual(task.scheduled_hours, round(expected, 2))
        task.with_company(self.company_b).invalidate_recordset(["scheduled_hours"])
        task.with_company(self.company_b).modified(["date_start"])
        self.env.flush_all()
        self.assertEqual(task.scheduled_hours, round(expected, 2))

    def test_an_assignee_company_without_calendar_counts_elapsed_hours(self) -> None:
        task = self._private_task(self.user_b)
        self.assertEqual(task.scheduled_hours, 24.0)

    def test_assignees_of_two_companies_read_the_creator_company(self) -> None:
        calendar = self.env.company.resource_calendar_id
        expected = calendar.get_work_hours_count(self.monday, self.tuesday)
        task = self._private_task(self.user_b | self.user_projectuser)
        self.assertEqual(task.scheduled_hours, round(expected, 2))
        task.with_user(self.user_b).modified(["date_start"])
        self.env.flush_all()
        self.assertEqual(task.scheduled_hours, round(expected, 2))

    def test_an_unassigned_task_reads_its_creator_company(self) -> None:
        project = self.env["project.project"].create(
            {
                "name": "No company",
                "company_id": False,
                "privacy_visibility": "employees",
            }
        )
        task = (
            self.env["project.task"]
            .with_user(self.user_b)
            .create(
                {
                    "name": "Created in B",
                    "project_id": project.id,
                    "date_start": self.monday,
                    "date_end": self.tuesday,
                    "user_ids": [Command.clear()],
                }
            )
        )
        self.assertFalse(task.company_id)
        self.assertEqual(task.scheduled_hours, 24.0)

    def test_the_value_does_not_depend_on_who_triggers_it(self) -> None:
        task = self._private_task(self.user_b)
        task.modified(["date_start"])
        self.env.flush_all()
        self.assertEqual(task.scheduled_hours, 24.0)


@tagged("post_install", "-at_install")
class TestPartnerPhonesEditable(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user_no_partner_write = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "No partner write",
                    "login": "no_partner_write",
                    "group_ids": [
                        Command.set(
                            [
                                cls.env.ref("base.group_user").id,
                                cls.env.ref("project.group_project_user").id,
                            ]
                        )
                    ],
                }
            )
        )
        cls.phone = cls.env["phone.number"].create({"number": "+52 55 1234 5678"})
        cls.task_1.partner_id = cls.partner_1

    def test_a_partner_writer_may_edit(self) -> None:
        task = self.task_1.with_user(self.user_projectuser)
        self.assertTrue(task.partner_phones_editable)
        task.phone_ids = [Command.link(self.phone.id)]
        self.assertIn(self.phone, self.partner_1.phone_ids)

    def test_a_user_who_cannot_write_the_partner_may_not(self) -> None:
        task = self.task_1.with_user(self.user_no_partner_write)
        self.assertFalse(task.partner_phones_editable)
        with self.assertRaises(AccessError):
            task.phone_ids = [Command.link(self.phone.id)]
            task.env.flush_all()

    def test_a_task_without_partner_is_editable(self) -> None:
        self.task_2.partner_id = False
        self.assertTrue(
            self.task_2.with_user(self.user_no_partner_write).partner_phones_editable
        )


@tagged("post_install", "-at_install")
class TestRecurrenceCompany(TestProjectCommon):
    def test_two_root_companies_are_refused_by_the_constraint(self) -> None:
        self.project_pigs.company_id = self.env.company
        other = self.env["res.company"].create({"name": "Other root"})
        project_other = self.env["project.project"].create(
            {"name": "Other", "company_id": other.id}
        )
        task = self.env["project.task"].create(
            {
                "name": "Recurring",
                "project_id": self.project_pigs.id,
                "date_end": datetime(2100, 1, 4),
                "recurring_task": True,
                "repeat_interval": 1,
                "repeat_unit": "week",
                "repeat_type": "forever",
            }
        )
        sibling = task.copy({"recurrence_id": task.recurrence_id.id})
        with self.assertRaisesRegex(ValidationError, "one company and its branches"):
            sibling.with_context(
                allowed_company_ids=[other.id, self.env.company.id]
            ).write({"project_id": project_other.id})
            self.env.flush_all()

    def test_one_root_with_a_branch_keeps_the_root(self) -> None:
        self.project_pigs.company_id = self.env.company
        branch = self.env["res.company"].create(
            {"name": "Branch", "parent_id": self.env.company.id}
        )
        project_branch = self.env["project.project"].create(
            {"name": "Branch project", "company_id": branch.id}
        )
        task = self.env["project.task"].create(
            {
                "name": "Recurring",
                "project_id": self.project_pigs.id,
                "date_end": datetime(2100, 1, 4),
                "recurring_task": True,
                "repeat_interval": 1,
                "repeat_unit": "week",
                "repeat_type": "forever",
            }
        )
        sibling = task.copy({"recurrence_id": task.recurrence_id.id})
        sibling.with_context(
            allowed_company_ids=[self.env.company.id, branch.id]
        ).project_id = project_branch
        self.env.flush_all()
        self.assertEqual(task.recurrence_id.company_id, self.env.company)


@tagged("post_install", "-at_install")
class TestCreateDerivedProject(TestProjectCommon):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        projects = cls.env["project.project"].create(
            [{"name": f"Parent project {i}"} for i in range(20)]
        )
        cls.parents = cls.env["project.task"].create(
            [
                {"name": f"Parent {i}", "project_id": project.id}
                for i, project in enumerate(projects)
            ]
        )

    def _count(self, vals_list):
        self.env.flush_all()
        with observing_statements():
            count0 = self.env.cr.sql_statement_count
            tasks = self.env["project.task"].create(vals_list)
            self.env.flush_all()
            return tasks, self.env.cr.sql_statement_count - count0

    def test_derived_projects_cost_what_explicit_ones_cost(self) -> None:
        _tasks, explicit = self._count(
            [
                {
                    "name": f"E{i}",
                    "parent_id": self.parents[i % 20].id,
                    "project_id": self.parents[i % 20].project_id.id,
                }
                for i in range(200)
            ]
        )
        tasks, derived = self._count(
            [
                {"name": f"C{i}", "parent_id": self.parents[i % 20].id}
                for i in range(200)
            ]
        )
        self.assertEqual(
            tasks.mapped("project_id"), self.parents.project_id, "projects derived"
        )
        self.assertLessEqual(derived, explicit + 10)

    def test_derived_rows_keep_their_per_project_defaults(self) -> None:
        self.parents[0].partner_id = self.partner_2
        tasks = self.env["project.task"].create(
            [
                {"name": "A", "parent_id": self.parents[0].id},
                {"name": "B", "parent_id": self.parents[1].id},
                {"name": "Private"},
            ]
        )
        a, b, private = tasks
        self.assertEqual(a.project_id, self.parents[0].project_id)
        self.assertEqual(b.project_id, self.parents[1].project_id)
        self.assertFalse(private.project_id)
        self.assertFalse(a.user_ids, "a subtask is not defaulted to its creator")
        self.assertFalse(b.user_ids)
        self.assertEqual(private.user_ids, self.env.user)
        self.assertEqual(a.partner_id, self.partner_2)
        self.assertFalse(a.display_in_project)
        self.assertEqual(
            a.step_id.id,
            self.env["project.task"]._get_default_step_id(a.project_id.id),
        )
        self.assertEqual(
            b.step_id.id,
            self.env["project.task"]._get_default_step_id(b.project_id.id),
        )


@tagged("post_install", "-at_install")
class TestTaskParentHashRole(TestProjectCommon):
    def _signed_by_project_link(self, role):
        _link, token = self.env["access.link"]._issue(
            self.project_pigs, partner=self.partner_2, role=role
        )
        pid = self.partner_2.id
        signature = self.project_pigs._sign_token(pid, token=token)
        return signature, pid, token

    def test_a_view_project_link_does_not_authorize_posting(self) -> None:
        signature, pid, token = self._signed_by_project_link("view")
        self.assertFalse(
            self.task_1._portal_verify_parent_hash(signature, pid, token=token)
        )

    def test_a_comment_project_link_authorizes_posting(self) -> None:
        signature, pid, token = self._signed_by_project_link("comment")
        self.assertTrue(
            self.task_1._portal_verify_parent_hash(signature, pid, token=token)
        )

    def test_an_edit_project_link_authorizes_posting(self) -> None:
        signature, pid, token = self._signed_by_project_link("edit")
        self.assertTrue(
            self.task_1._portal_verify_parent_hash(signature, pid, token=token)
        )
