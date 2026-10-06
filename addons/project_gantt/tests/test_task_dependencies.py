from markupsafe import Markup

from odoo.fields import Command
from odoo.tests import tagged

from .gantt_reschedule_dates_common import ProjectGanttRescheduleCommon


@tagged("-at_install", "post_install")
class TestTaskDependencies(ProjectGanttRescheduleCommon):
    def test_task_dependencies_display_warning_dependency_in_gantt(self):
        self.task_1.write({"state": "in_progress"})
        self.assertTrue(
            self.task_1.display_warning_dependency_in_gantt,
            "display_warning_dependency_in_gantt should be True if the task state is neither done or canceled",
        )
        self.task_1.write({"state": "done"})
        self.assertFalse(
            self.task_1.display_warning_dependency_in_gantt,
            "display_warning_dependency_in_gantt should be False if the task state is done",
        )

    def test_tasks_dependencies_warning_when_planning(self):
        self.task_4.write({"predecessor_ids": [Command.link(self.task_1.id)]})
        self.assertFalse(self.task_4.dependency_warning)
        self.task_5.write({"predecessor_ids": False})
        self.task_4.write({"predecessor_ids": [Command.link(self.task_5.id)]})
        self.assertEqual(
            self.task_4.dependency_warning,
            Markup(
                "<p>This task cannot be planned before the following tasks on which it depends: %s</p>"
            )
            % (self.task_5.name),
        )
