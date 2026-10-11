from odoo.tests import tagged

from odoo.addons.project_gantt.tests.test_task_gantt_view import TestTaskGanttView


@tagged("-at_install", "post_install")
class TestTaskAllocatedHours(TestTaskGanttView):
    def test_estimate_is_not_reduced_by_a_sibling_estimate(self):
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
        )
        self.assertEqual(self.tasks.mapped("planned_hours"), [16.0, 16.0, 12.0])
        self.assertEqual(
            self.tasks.mapped("planned_hours_manual"), [False, False, True]
        )
