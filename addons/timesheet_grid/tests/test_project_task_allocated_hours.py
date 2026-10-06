from odoo.tests import tagged

from odoo.addons.project_gantt.tests.test_task_gantt_view import TestTaskGanttView


@tagged("-at_install", "post_install")
class TestTaskAllocatedHours(TestTaskGanttView):
    def test_estimate_is_not_reduced_by_a_sibling_estimate(self):
        """An existing estimate on one task does not shrink the others.

        The capacity of the window used to be shared out: a task already
        carrying 12h left only 4h to split between the other two. project.task
        now derives each estimate from its own window (planned_hours =
        scheduled_hours x planned_resources x units), so a sibling's figure is
        irrelevant -- and an estimate entered by hand is an override that
        outlives the dates (`planned_hours_manual`), which is why the 12h task
        keeps its 12h while the two without an estimate take the window's 16h.
        """
        self.tasks |= self.env["project.task"].create(
            {
                "name": "Test gantt",
                "project_id": self.project_gantt_test_1.id,
                "planned_hours": 12.0,
            }
        )
        self.tasks.write(
            {
                "user_ids": [self.project_gantt_test_1.user_id.id],
                "date_start": "2024-03-07 00:00:00",
                "date_end": "2024-03-08 23:59:59",
            }
        )  # 16 working hours in the window
        self.assertEqual(self.tasks.mapped("planned_hours"), [16.0, 16.0, 12.0])
        self.assertEqual(
            self.tasks.mapped("planned_hours_manual"), [False, False, True]
        )
