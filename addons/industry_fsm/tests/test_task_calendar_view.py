from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo.tests import Form

from odoo.addons.project.tests.test_project_base import TestProjectCommon


class TestTaskCalendarView(TestProjectCommon):
    def test_simulate_task_creation_from_calendar(self):
        """
        Create a task in the task form 2, form called from the calendar view, and apply the same context as the calendar would.
        """
        now = datetime.combine(datetime.now(), datetime.min.time())
        # The keys the calendar view actually emits: its arch is
        # date_start="date_start_effective" date_stop="date_end", and
        # ProjectTaskCalendarModel.makeContextDefaults forwards the former onto
        # default_date_start. Naming fields this fork does not have made the
        # context inert, so the test applied one no calendar produces.
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
        task_form.user_ids = self.env.user
        task = task_form.save()

        self.assertEqual(task.date_start, now)
