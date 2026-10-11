from datetime import datetime

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TestCommonForecast


@tagged("-at_install", "post_install")
class TestForecastCreationAndEditing(TestCommonForecast):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.classPatch(cls.env.cr, "now", fields.Datetime.now)
        with freeze_time("2019-01-01"):
            cls.setUpEmployees()
            cls.setUpProjects()

        cls.slot = cls.env["planning.slot"].create(
            {
                "project_id": cls.project_opera.id,
                "resource_id": cls.employee_bert.resource_id.id,
                "start_datetime": datetime(
                    2019, 6, 6, 8, 0, 0
                ),
                "end_datetime": datetime(2019, 6, 6, 17, 0, 0),
            }
        )

    def test_creating_a_planning_shift_allocated_hours_are_correct(self):
        self.assertEqual(
            self.slot.allocated_hours, 8.0, "resource hours should be a full workday"
        )

        self.slot.write({"allocated_percentage": 50})
        self.assertEqual(
            self.slot.allocated_hours, 4.0, "resource hours should be a half duration"
        )

        values = {
            "allocated_percentage": 100,
            "start_datetime": datetime(2019, 6, 2, 8, 0, 0),
            "end_datetime": datetime(
                2019, 6, 2, 17, 0, 0
            ),
        }
        self.slot.write(values)

        self.assertEqual(
            self.slot.allocated_hours,
            0,
            "resource hours should be a full day working hours",
        )

        values = {
            "allocated_percentage": 100,
            "start_datetime": datetime(2019, 6, 3, 0, 0, 0),
            "end_datetime": datetime(
                2019, 6, 8, 23, 59, 0
            ),
        }
        self.slot.write(values)

        self.assertEqual(
            self.slot.allocated_hours,
            40,
            "resource hours should be a full week's available hours",
        )

    def test_creating_a_planning_shift_with_flexible_hours_allocated_hours_are_correct(
        self,
    ):
        self.employee_bert.resource_id.calendar_id.schedule_type = "flexible"
        self.assertEqual(
            self.slot.allocated_hours, 8.0, "resource hours should be a full workday"
        )

        self.slot.write({"allocated_percentage": 50})
        self.assertEqual(
            self.slot.allocated_hours, 4.0, "resource hours should be a half duration"
        )

        values = {
            "allocated_percentage": 100,
            "start_datetime": datetime(2019, 6, 2, 8, 0, 0),
            "end_datetime": datetime(
                2019, 6, 2, 17, 0, 0
            ),
        }
        self.slot.write(values)

        self.assertEqual(
            self.slot.allocated_hours,
            8,
            "resource hours should be a full day working hours",
        )

        values = {
            "allocated_percentage": 100,
            "start_datetime": datetime(2019, 6, 3, 0, 0, 0),
            "end_datetime": datetime(
                2019, 6, 8, 23, 0, 0
            ),
        }
        self.slot.write(values)
        self.assertEqual(
            self.slot.allocated_hours,
            self.employee_bert.resource_id.calendar_id.hours_per_week,
            "flexible resources have a week rate limit defined in the contract, 40 hours in this case",
        )

    @freeze_time("2023-11-20")
    def test_shift_creation_from_project(self):
        self.env.user.tz = "Asia/Kolkata"
        self.env.user.company_id.resource_calendar_id.tz = "Asia/Kolkata"
        PlanningTemplate = self.env["planning.slot.template"]
        Project = self.env["project.project"]

        project_a = Project.create({"name": "project_a"})
        project_b = Project.create({"name": "project_b"})

        template_a = PlanningTemplate.create(
            {
                "start_time": 8,
                "end_time": 10,
                "duration_days": 1,
                "project_id": project_a.id,
            }
        )
        self.assertEqual(
            template_a.duration_days,
            1,
            "Duration in days should be a 1 day according to resource calendar.",
        )
        self.assertEqual(
            template_a.end_time, 10.0, "End time should be 2 hours from start hours."
        )

        template_b = PlanningTemplate.create(
            {
                "start_time": 8,
                "end_time": 12,
                "duration_days": 1,
                "project_id": project_b.id,
            }
        )
        slot = self.env["planning.slot"].create({"template_id": template_a.id})
        self.assertEqual(
            slot.project_id.id,
            slot.template_autocomplete_ids.mapped("project_id").id,
            "Project of the slot and shift template should be same.",
        )

        slot.template_id = template_b.id
        self.assertEqual(
            slot.project_id.id,
            slot.template_autocomplete_ids.mapped("project_id").id,
            "Project of the slot and shift template should be same.",
        )

    def test_removing_template_clears_project_id(self):
        project_a = self.env["project.project"].create({"name": "project_a"})
        template_a = self.env["planning.slot.template"].create(
            {
                "start_time": 8,
                "end_time": 10,
                "duration_days": 1,
                "project_id": project_a.id,
            }
        )
        slot = self.env["planning.slot"].create({"template_id": template_a.id})
        self.assertEqual(
            slot.project_id, project_a, "Slot should inherit the template's project."
        )

        slot.template_id = False
        self.assertFalse(
            slot.project_id,
            "Removing the template should clear the project_id it set, "
            "since the user never changed it by hand.",
        )

    def test_default_project_id_context_sets_project_on_creation(self):
        project_a = self.env["project.project"].create({"name": "project_a"})
        slot = (
            self.env["planning.slot"]
            .with_context(default_project_id=project_a.id)
            .create(
                {
                    "resource_id": self.employee_bert.resource_id.id,
                    "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 6, 17, 0, 0),
                }
            )
        )
        self.assertEqual(
            slot.project_id,
            project_a,
            "A slot created without a template should fall back to "
            "default_project_id from the context.",
        )

    def test_consistency_change_project_company(self):
        new_company = self.env["res.company"].create({"name": "New Company"})
        with self.assertRaises(UserError):
            self.project_opera.company_id = new_company

    @freeze_time("2019-06-06")
    def test_auto_plan_closest_shift_from_same_project(self):
        project = self.env["project.project"].create({"name": "Planning Project"})
        *_dummy, slot_to_plan = self.env["planning.slot"].create(
            [
                {
                    "project_id": project.id,
                    "resource_id": self.employee_bert.resource_id.id,
                    "start_datetime": datetime(2019, 6, 3, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 3, 9, 0, 0),
                },
                {
                    "project_id": project.id,
                    "resource_id": self.employee_janice.resource_id.id,
                    "start_datetime": datetime(2019, 6, 4, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 4, 9, 0, 0),
                },
                {
                    "project_id": project.id,
                    "resource_id": self.employee_joseph.resource_id.id,
                    "start_datetime": datetime(2019, 6, 5, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 5, 9, 0, 0),
                },
                {
                    "project_id": project.id,
                    "start_datetime": datetime(2019, 6, 6, 8, 0, 0),
                    "end_datetime": datetime(2019, 6, 6, 9, 0, 0),
                },
            ]
        )
        slot_to_plan.auto_plan_id()
        self.assertEqual(
            slot_to_plan.resource_id,
            self.employee_joseph.resource_id,
            "The shift to plan should be linked to the resource of the closest shift (whose deadline is the closest "
            "from the current date) of the same project.",
        )
