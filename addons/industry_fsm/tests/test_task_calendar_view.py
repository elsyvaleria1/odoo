from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo.tests import Form

from odoo.addons.project.tests.test_project_base import (
    TestProjectCommon,
    assign_in_form,
)


class TestTaskCalendarView(TestProjectCommon):
    def test_simulate_task_creation_from_calendar(self):
        now = datetime.combine(datetime.now(), datetime.min.time())
        default_date_start = now + relativedelta(days=3, hour=7)
        default_date_end = now + relativedelta(days=3, hour=19)
        calendar_ctx = {
            "default_date_start_effective": default_date_start,
            "default_date_start": default_date_start,
            "default_date_end": default_date_end,
        }

        task_form = Form(
            self.env["project.task"].with_context(calendar_ctx),
            view="project.view_task_form2",
        )
        task_form.name = "Test Task 1"
        task_form.project_id = self.project_pigs
        task_form.date_start = now
        task_form.date_end = now + relativedelta(days=1)
        task_form.partner_id = self.partner_1
        assign_in_form(task_form, self.env.user)
        task = task_form.save()

        self.assertEqual(task.date_start, now)
