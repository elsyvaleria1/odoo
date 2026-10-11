from datetime import datetime, timedelta

from odoo.fields import Datetime
from odoo.tests import tagged

from .common import TestIndustryFsmCommon


@tagged("-at_install", "post_install")
class TestTaskGroupExpand(TestIndustryFsmCommon):
    def test_task_user_ids_group_expand(self):
        gantt_domain = [
            ("date_start", ">=", datetime.today()),
            ("date_end", "<=", datetime.today() + timedelta(days=7)),
        ]
        Task = self.env["project.task"].with_context(
            {
                "gantt_start_date": datetime.today(),
                "fsm_mode": True,
                "gantt_scale": "week",
                "read_group_expand": True,
            }
        )

        Task.create(
            [
                {
                    "name": "planned task",
                    "project_id": self.fsm_project.id,
                    "partner_id": self.partner.id,
                    "date_start": datetime.today() + timedelta(days=1),
                    "date_end": datetime.today() + timedelta(days=2),
                    "user_ids": [self.george_user.id],
                },
                {
                    "name": "non-planned task",
                    "project_id": self.fsm_project.id,
                    "partner_id": self.partner.id,
                    "user_ids": [self.marcel_user.id],
                },
            ]
        )

        groups = Task.formatted_read_group(gantt_domain, ["user_ids"])
        user_ids_in_group = [
            group["user_ids"][0] for group in groups if group["user_ids"]
        ]

        self.assertIn(
            self.george_user.id,
            user_ids_in_group,
            "A group should exist for the user if they have a planned task whithin the gantt period.",
        )

        self.assertIn(
            self.marcel_user.id,
            user_ids_in_group,
            "A group should exist for the user if they have a task in an open stage whithin the gantt period.",
        )

        self.assertNotIn(
            self.henri_user.id,
            user_ids_in_group,
            "A group should not exist for the user if they don't have a task whithin the gantt period.",
        )

    def test_project_ids_group_expand(self):
        Task = self.env["project.task"]
        project, unscheduled_fsm_project = self.env["project.project"].create(
            [
                {
                    "name": "Project",
                },
                {
                    "name": "Test FSM Project",
                    "is_fsm": True,
                    "company_id": self.env.company.id,
                },
            ]
        )
        Task.create(
            [
                {
                    "name": "fsm task",
                    "project_id": self.fsm_project.id,
                    "date_start": Datetime.to_datetime("2023-01-02"),
                    "date_end": Datetime.to_datetime("2023-01-03"),
                },
                {
                    "name": "non-fsm task",
                    "project_id": project.id,
                    "date_start": Datetime.to_datetime("2023-01-02"),
                    "date_end": Datetime.to_datetime("2023-01-03"),
                },
            ]
        )
        context = {
            "gantt_start_date": Datetime.to_datetime("2023-02-01"),
            "gantt_scale": "week",
            "fsm_mode": True,
        }
        domain = [
            ("project_id", "!=", False),
            ("date_start", ">=", Datetime.to_datetime("2023-01-01")),
            ("date_end", "<=", Datetime.to_datetime("2023-01-04")),
        ]

        displayed_gantt_projects = Task.with_context(context)._group_expand_project_ids(
            None, domain
        )
        self.assertTrue(
            self.fsm_project in displayed_gantt_projects,
            "Project 1 should be displayed in the Gantt view",
        )
        self.assertFalse(
            project in displayed_gantt_projects,
            "Project 2 should not be displayed in the Gantt view",
        )
        displayed_gantt_projects = Task.with_context(context)._group_expand_project_ids(
            None, [("project_id", "ilike", "Test")] + domain
        )
        self.assertTrue(
            unscheduled_fsm_project in displayed_gantt_projects,
            "Project 1 should be displayed in the Gantt view",
        )
