from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo.addons.project.tests.test_project_base import TestProjectCommon


class TestSmartScheduleCommon(TestProjectCommon):
    @classmethod
    def _resource_of(cls, user):
        resource = user.resource_ids.filtered(
            lambda resource: resource.company_id == user.company_id
        )[:1]
        if resource:
            resource.calendar_id = cls.project_pigs.resource_calendar_id
            if user.tz:
                resource.tz = user.tz
            return resource
        return cls.env["resource.resource"].create(
            {
                "calendar_id": cls.project_pigs.resource_calendar_id.id,
                "company_id": user.company_id.id,
                "name": user.name,
                "user_id": user.id,
                "tz": user.tz,
            }
        )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.projectuser_resource = cls._resource_of(cls.user_projectuser)
        cls.projectmanager_resource = cls._resource_of(cls.user_projectmanager)

        tasks = cls.env["project.task"].create(
            [
                {
                    "name": "task_project_pigs_with_planned_hours_user",
                    "planned_hours": 8,
                    "project_id": cls.project_pigs.id,
                    "user_ids": [cls.user_projectuser.id],
                },
                {
                    "name": "task_project_pigs_with_planned_hours_manager",
                    "planned_hours": 10,
                    "project_id": cls.project_pigs.id,
                    "user_ids": [cls.user_projectmanager.id],
                },
                {
                    "name": "task_project_pigs_with_planned_hours_no_user",
                    "planned_hours": 10,
                    "project_id": cls.project_pigs.id,
                    "user_ids": None,
                },
                {
                    "name": "task_project_pigs_no_planned_hours_user",
                    "project_id": cls.project_pigs.id,
                    "user_ids": [cls.user_projectuser.id],
                },
                {
                    "name": "task_project_pigs_no_planned_hours_manager",
                    "project_id": cls.project_pigs.id,
                    "user_ids": [cls.user_projectmanager.id],
                },
                {
                    "name": "task_project_pigs_no_planned_hours_no_user",
                    "project_id": cls.project_pigs.id,
                    "user_ids": None,
                },
                {
                    "name": "task_project_goats_with_planned_hours_user",
                    "project_id": cls.project_goats.id,
                    "planned_hours": 10,
                    "user_ids": [cls.user_projectuser.id],
                },
                {
                    "name": "task_project_goats_no_planned_hours_user",
                    "project_id": cls.project_goats.id,
                    "user_ids": [cls.user_projectuser.id],
                },
            ]
        )

        (
            cls.task_project_pigs_with_planned_hours_user,
            cls.task_project_pigs_with_planned_hours_manager,
            cls.task_project_pigs_with_planned_hours_no_user,
            cls.task_project_pigs_no_planned_hours_user,
            cls.task_project_pigs_no_planned_hours_manager,
            cls.task_project_pigs_no_planned_hours_no_user,
            cls.task_project_goats_with_planned_hours_user,
            cls.task_project_goats_no_planned_hours_user,
        ) = tasks

        cls.start_date_view = datetime.now()
        cls.end_date_view = cls.start_date_view + relativedelta(days=31)
        cls.start_date_view_str = cls.start_date_view.strftime("%Y-%m-%d %H:%M:%S")
        cls.end_date_view_str = cls.end_date_view.strftime("%Y-%m-%d %H:%M:%S")
        cls.is_module_timesheet_grid_installed = hasattr(
            cls.env["project.task"], "allow_timesheets"
        )
