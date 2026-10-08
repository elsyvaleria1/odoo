from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import tagged

from .test_project_base import TestProjectCommon


@tagged("post_install", "-at_install")
class TestProjectReviewMilestones(TestProjectCommon):
    def setUp(self) -> None:
        super().setUp()
        self.env.user.group_ids |= self.env.ref("project.group_project_milestone")
        self.project = self.env["project.project"].create(
            {"name": "Milestones", "allow_milestones": True}
        )
        today = fields.Date.today()
        Milestone = self.env["project.milestone"]
        self.overdue = Milestone.create(
            {
                "name": "Overdue later",
                "project_id": self.project.id,
                "sequence": 10,
                "date_deadline": today - relativedelta(days=1),
            }
        )
        self.first = Milestone.create(
            {
                "name": "First",
                "project_id": self.project.id,
                "sequence": 1,
                "date_deadline": today + relativedelta(days=10),
            }
        )
        self.env["project.task"].create(
            {
                "name": "Done",
                "project_id": self.project.id,
                "milestone_id": self.first.id,
                "state": "done",
            }
        )

    def test_next_milestone_follows_the_milestone_order(self) -> None:
        self.assertEqual(self.project.next_milestone_id, self.first)

    def test_indicators_describe_the_next_milestone(self) -> None:
        self.assertFalse(self.project.is_milestone_deadline_exceeded)
        self.assertTrue(self.project.can_mark_milestone_as_done)

    def test_indicators_flag_an_overdue_next_milestone(self) -> None:
        self.first.is_reached = True
        self.project.invalidate_recordset()
        self.assertEqual(self.project.next_milestone_id, self.overdue)
        self.assertTrue(self.project.is_milestone_deadline_exceeded)
        self.assertFalse(self.project.can_mark_milestone_as_done)


@tagged("post_install", "-at_install")
class TestProjectReviewCounts(TestProjectCommon):
    def test_counts_follow_their_records(self) -> None:
        self.env.user.group_ids |= self.env.ref("project.group_project_milestone")
        project = self.env["project.project"].create(
            {"name": "Counted", "allow_milestones": True}
        )
        self.env["project.milestone"].create(
            [
                {"name": "M1", "project_id": project.id},
                {"name": "M2", "project_id": project.id},
            ]
        )
        self.env["project.update"].create(
            {"name": "U", "project_id": project.id, "status": "on_track"}
        )
        self.env["project.retrospective"].create(
            [
                {"name": "R1", "project_id": project.id},
                {"name": "R2", "project_id": project.id},
                {"name": "R3", "project_id": project.id},
            ]
        )
        self.assertEqual(project.milestone_count, 2)
        self.assertEqual(project.update_count, 1)
        self.assertEqual(project.retrospective_count, 3)

    def test_count_fields_are_declarative(self) -> None:
        Project = self.env["project.project"]
        for fname, count_of in (
            ("milestone_count", "milestone_ids"),
            ("update_count", "update_ids"),
            ("retrospective_count", "retrospective_ids"),
        ):
            with self.subTest(field=fname):
                self.assertEqual(Project._fields[fname].type, "integer")
                self.assertEqual(Project._fields[fname].count_of, count_of)
        self.assertEqual(
            Project._fields["milestone_count"].groups, "project.group_project_milestone"
        )
