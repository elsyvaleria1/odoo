from datetime import datetime

from odoo.addons.project.tests.test_project_base import TestProjectCommon


class TestProjectGanttProgressBarFlow(TestProjectCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._employ(cls.user_projectuser)
        cls.project_goats.write(
            {
                "user_id": cls.user_projectuser.id,
                "date_start": "2024-11-27 06:00:00",
                "date": "2024-11-28 15:00:00",
                "allocated_hours": 16,
            }
        )
        cls.project_pigs.write(
            {
                "user_id": cls.user_projectmanager.id,
                "date_start": "2024-11-27 06:00:00",
                "date": "2024-11-28 15:00:00",
                "allocated_hours": 14,
            }
        )
        cls.user_ids = (cls.user_projectuser + cls.user_projectmanager).ids
        cls.start, cls.stop = datetime(2024, 11, 26), datetime(2024, 12, 2, 23, 59, 59)

    def test_user_projectuser_can_see_progress_bar(self):
        progress_bar = (
            self.env["project.project"]
            .with_user(self.user_projectuser)
            ._gantt_progress_bar("user_id", self.user_ids, self.start, self.stop)
        )
        self.assertDictEqual(
            progress_bar,
            {
                self.user_projectuser.id: {"value": 16.0, "max_value": 40.0},
                self.user_projectmanager.id: {"value": 14.0, "max_value": 40.0},
                "warning": "This user isn't expected to have any projects assigned during this period because they don't have any running contract.",
            },
            "The progress bar should correctly display values for the assigned users and include a warning for unassigned users.",
        )

    def test_portal_user_cannot_access_progress_bar(self):
        progress_bar_data = (
            self.env["project.project"]
            .with_user(self.user_portal)
            ._gantt_progress_bar("user_id", self.user_ids, self.start, self.stop)
        )
        self.assertFalse(
            progress_bar_data, "Progress bar should be empty for non-project users"
        )

    def test_gantt_progress_bar(self):

        progress_bar_data = self.env["project.project"]._gantt_progress_bar(
            "user_id", self.user_ids, self.start, self.stop
        )

        self.assertDictEqual(
            {"value": 16.0, "max_value": 40.0},
            progress_bar_data[self.user_projectuser.id],
            "user_projectuser should have 16 hours planned initially",
        )
        self.assertDictEqual(
            {"value": 14.0, "max_value": 40.0},
            progress_bar_data[self.user_projectmanager.id],
            "user_projectmanager should have 14 hours planned initially",
        )

        self.env["project.project"].create(
            [
                {
                    "name": "Project-1",
                    "user_id": self.user_projectuser.id,
                    "date_start": "2024-11-29 04:00:00",
                    "date": "2024-11-29 08:00:00",
                    "allocated_hours": 5,
                },
                {
                    "name": "Project-2",
                    "user_id": self.user_projectmanager.id,
                    "date_start": "2024-11-29 10:00:00",
                    "date": "2024-11-29 15:00:00",
                    "allocated_hours": 4,
                },
            ]
        )

        progress_bar_data = self.env["project.project"]._gantt_progress_bar(
            "user_id", self.user_ids, self.start, self.stop
        )

        self.assertDictEqual(
            {"value": 21.0, "max_value": 40.0},
            progress_bar_data[self.user_projectuser.id],
            "After adding new projects, user_projectuser should have 21 hours planned in the specified date range",
        )
        self.assertDictEqual(
            {"value": 18.0, "max_value": 40.0},
            progress_bar_data[self.user_projectmanager.id],
            "After adding new projects, user_projectmanager should have 18 hours planned in the specified date range",
        )

        self.env["project.project"].create(
            [
                {
                    "name": "Project-3",
                    "user_id": self.user_projectuser.id,
                    "date_start": "2024-12-01 08:00:00",
                    "date": "2024-12-01 14:00:00",
                    "allocated_hours": 7,
                },
                {
                    "name": "Project-3",
                    "user_id": self.user_projectmanager.id,
                    "date_start": "2024-12-01 08:00:00",
                    "date": "2024-12-01 15:00:00",
                    "allocated_hours": 8,
                },
                {
                    "name": "Project-4",
                    "user_id": self.user_projectuser.id,
                    "date_start": "2024-12-05 08:00:00",
                    "date": "2024-12-05 14:00:00",
                    "allocated_hours": 7,
                },
                {
                    "name": "Project-5",
                    "user_id": self.user_projectmanager.id,
                    "date_start": "2024-12-06 08:00:00",
                    "date": "2024-12-06 15:00:00",
                    "allocated_hours": 8,
                },
            ]
        )

        progress_bar_data = self.env["project.project"]._gantt_progress_bar(
            "user_id", self.user_ids, self.start, self.stop
        )

        self.assertDictEqual(
            {"value": 28.0, "max_value": 40.0},
            progress_bar_data[self.user_projectuser.id],
            "After all updates, user_projectuser should have 28 hours planned in the specified date range",
        )
        self.assertDictEqual(
            {"value": 26.0, "max_value": 40.0},
            progress_bar_data[self.user_projectmanager.id],
            "After all updates, user_projectmanager should have 26 hours planned in the specified date range",
        )
