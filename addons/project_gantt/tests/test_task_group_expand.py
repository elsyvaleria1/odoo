from datetime import datetime, timedelta

from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.project.tests.test_project_base import TestProjectCommon


@tagged("-at_install", "post_install")
class TestTaskGroupExpand(TestProjectCommon):
    def test_task_user_ids_group_expand(self):
        def user_in_groups(user_id):
            return any(
                "user_ids" in group and group["user_ids"][0] == user_id
                for group in groups
            )

        gantt_domain = [
            ("date_start", ">=", datetime.today()),
            ("date_end", "<=", datetime.today() + timedelta(days=7)),
        ]
        Task = (
            self.env["project.task"]
            .with_user(self.user_projectuser)
            .with_context(
                {
                    "gantt_start_date": datetime.today(),
                    "gantt_scale": "week",
                    "read_group_expand": True,
                }
            )
        )

        groups = Task.formatted_read_group(
            gantt_domain + [("id", "=", self.task_2.id)], ["user_ids"]
        )
        self.assertTrue(
            user_in_groups(self.user_projectuser.id),
            "A group should exist for the current user if no filter is applied on user_ids.",
        )

        groups = Task.formatted_read_group(
            gantt_domain + [("user_ids", "in", self.user_projectmanager.id)],
            ["user_ids"],
        )
        self.assertFalse(
            user_in_groups(self.user_projectuser.id),
            "No empty group should be added for the current user if a filter is applied on user_ids.",
        )

        test_task = self.env["project.task"].create(
            [
                {
                    "name": "Shared task test group expand",
                    "user_ids": [
                        Command.set(
                            [self.user_projectuser.id, self.user_projectmanager.id]
                        )
                    ],
                }
            ]
        )
        groups = Task.formatted_read_group(
            gantt_domain + [("user_ids", "in", self.user_projectmanager.id)],
            ["user_ids"],
        )
        self.assertFalse(
            user_in_groups(self.user_projectuser.id),
            "No empty group should be added for the current user if a filter is applied on user_ids, even if a record not visible in the gantt view match the domain.",
        )

        test_task.write(
            {
                "date_start": datetime.now(),
                "date_end": datetime.now() + timedelta(days=2),
            }
        )
        groups = Task.formatted_read_group(
            gantt_domain + [("user_ids", "in", self.user_projectmanager.id)],
            ["user_ids"],
        )
        self.assertTrue(
            user_in_groups(self.user_projectuser.id),
            "Even if a filter is applied on user_ids, all user row containing visible tasks in the gantt view should be displayed",
        )

        user_no_task = self.user_portal
        search_domain = [
            ("user_ids", "in", user_no_task.id),
            ("date_start", ">=", datetime.today()),
            ("date_end", "<=", datetime.today() + timedelta(days=7)),
        ]
        groups = Task.formatted_read_group(search_domain, ["user_ids"])
        self.assertTrue(
            user_in_groups(user_no_task.id),
            "The row for searched user should appear even if they have no task.",
        )
