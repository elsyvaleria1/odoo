from datetime import datetime

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo.tests import TransactionCase

from odoo.addons.mail.tests.common import mail_new_test_user


class TestGanttProgressBar(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.resource_calendar_id.tz = "Europe/Brussels"
        cls.project_user = mail_new_test_user(
            cls.env,
            login="Armande",
            name="Armande Project_user",
            email="armande.project_user@example.com",
            notification_type="inbox",
            groups="project.group_project_user",
        )

        cls.project_test_user = mail_new_test_user(
            cls.env,
            login="Armando",
            name="Armando Project_user",
            email="armando.project_user@example.com",
            notification_type="inbox",
            groups="project.group_project_user",
        )

        cls.project_test = cls.env["project.project"].create(
            {
                "name": "Project Test",
            }
        )

        cls.portal_user = mail_new_test_user(
            cls.env,
            login="portal_project",
            name="Portal_user",
            email="portal_project_user@example.com",
            notification_type="email",
            groups="base.group_portal",
        )

    def create_tasks(self, nb=40):
        now = datetime.combine(datetime.now(), datetime.min.time())
        hour_start = [6, 11]
        hour_end = [10, 15]
        users = [
            self.project_test_user,
            self.project_user,
            self.project_user | self.project_test_user,
        ]

        self.env["project.task"].with_context(tracking_disable=True).create(
            [
                {
                    "name": "Fsm task " + str(i),
                    "user_ids": users[i % 3],
                    "project_id": self.project_test.id,
                    "date_start": now
                    + relativedelta(days=i / 2, hour=hour_start[i % 2]),
                    "date_end": now + relativedelta(days=i / 2, hour=hour_end[i % 2]),
                }
                for i in range(nb)
            ]
        )

    @freeze_time("2023-01-02")
    def test_gantt_progress_bar(self):
        self.env["project.task"].create(
            [
                {
                    "name": "Task 1",
                    "user_ids": self.project_user,
                    "project_id": self.project_test.id,
                    "date_start": "2021-09-24 06:00:00",
                    "date_end": "2021-09-24 15:00:00",
                    "planned_hours": 8,
                },
                {
                    "name": "Task 2",
                    "user_ids": self.project_user,
                    "project_id": self.project_test.id,
                    "date_start": "2021-09-27 06:00:00",
                    "date_end": "2021-09-28 15:00:00",
                    "planned_hours": 16,
                },
                {
                    "name": "Task 3",
                    "user_ids": self.project_user,
                    "project_id": self.project_test.id,
                    "date_start": "2021-09-29 05:00:00",
                    "date_end": "2021-09-29 08:00:00",
                    "planned_hours": 3,
                },
                {
                    "name": "Task 4",
                    "user_ids": self.project_user,
                    "project_id": self.project_test.id,
                    "date_start": "2021-09-30 12:00:00",
                    "date_end": "2021-09-30 15:00:00",
                    "planned_hours": 3,
                },
            ]
        )

        start, stop = datetime(2021, 9, 26), datetime(2021, 10, 2, 23, 59, 59)
        progress_bar = self.env["project.task"]._gantt_progress_bar(
            "user_ids", self.project_user.ids, start, stop
        )
        self.assertEqual(
            22,
            progress_bar[self.project_user.id]["value"],
            "User should have 22 hours planned on this period",
        )
        self.assertEqual(
            40,
            progress_bar[self.project_user.id]["max_value"],
            "User is expected to work 40 hours on this period",
        )

        self.env["project.task"].create(
            [
                {
                    "name": "Task 5",
                    "user_ids": self.project_user,
                    "project_id": self.project_test.id,
                    "date_start": "2021-10-02 06:00:00",
                    "date_end": "2021-10-02 15:00:00",
                    "planned_hours": 8,
                }
            ]
        )

        progress_bar = self.env["project.task"]._gantt_progress_bar(
            "user_ids", self.project_user.ids, start, stop
        )
        self.assertEqual(
            30,
            progress_bar[self.project_user.id]["value"],
            "User should have 30 hours planned on this period",
        )
        self.assertEqual(
            40,
            progress_bar[self.project_user.id]["max_value"],
            "User is expected to work 40 hours on this period",
        )

        self.env["project.task"].create(
            [
                {
                    "name": "Task 6",
                    "user_ids": self.project_user,
                    "project_id": self.project_test.id,
                    "date_start": "2021-09-24 06:00:00",
                    "date_end": "2021-09-27 15:00:00",
                    "planned_hours": 16,
                }
            ]
        )

        progress_bar = self.env["project.task"]._gantt_progress_bar(
            "user_ids", self.project_user.ids, start, stop
        )
        self.assertEqual(
            38,
            progress_bar[self.project_user.id]["value"],
            "User should have 38 hours planned on this period",
        )
        self.assertEqual(
            40,
            progress_bar[self.project_user.id]["max_value"],
            "User is expected to work 40 hours on this period",
        )

    def test_project_user_can_see_progress_bar(self):
        self.env["project.task"].create(
            [
                {
                    "name": "Task 1",
                    "user_ids": self.project_user,
                    "project_id": self.project_test.id,
                    "date_start": "2021-09-27 06:00:00",
                    "date_end": "2021-09-28 15:00:00",
                    "planned_hours": 16,
                }
            ]
        )

        progress_bar = (
            self.env["project.task"]
            .with_user(self.project_test_user)
            ._gantt_progress_bar(
                "user_ids",
                self.project_user.ids,
                datetime(2021, 9, 26),
                datetime(2021, 10, 2, 23, 59, 59),
            )
        )
        self.assertEqual(
            16,
            progress_bar[self.project_user.id]["value"],
            "User should have 16 hours planned on this period",
        )
        self.assertEqual(
            40,
            progress_bar[self.project_user.id]["max_value"],
            "User is expected to work 40 hours on this period",
        )

    def test_portal_user_cannot_see_progress_bar(self):
        self.env["project.task"].create(
            [
                {
                    "name": "Task 1",
                    "user_ids": self.project_user,
                    "project_id": self.project_test.id,
                    "date_start": "2021-09-27 06:00:00",
                    "date_end": "2021-09-28 15:00:00",
                    "planned_hours": 16,
                }
            ]
        )

        progress_bar = (
            self.env["project.task"]
            .with_user(self.portal_user)
            ._gantt_progress_bar(
                "user_ids",
                self.project_user.ids,
                datetime(2021, 9, 26),
                datetime(2021, 10, 2, 23, 59, 59),
            )
        )
        self.assertFalse(
            progress_bar, "Progress bar should be empty for non-project users"
        )

    def test_performance(self):
        nb = 40
        self.create_tasks(nb=nb)
        start = datetime.combine(datetime.now(), datetime.min.time()) + relativedelta(
            days=-1
        )
        end = start + relativedelta(days=nb / 2 + 1)
        users = self.project_user | self.project_test_user

        with self.assertQueryCount(__system__=9):
            # Query count should be stable even if the number of tasks or users increase (progress bar query count is O(1))
            progress_bar = self.env["project.task"]._gantt_progress_bar(
                "user_ids", users.ids, start, end
            )

        self.assertEqual(len(progress_bar), 3)  # 2 users + 1 warning
