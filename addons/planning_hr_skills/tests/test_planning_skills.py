from datetime import date, datetime

from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPlanningSkills(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        skill_type = cls.env["hr.skill.type"].create(
            {
                "name": "Planning languages",
                "skill_ids": [Command.create({"name": "Quechua"})],
                "skill_level_ids": [
                    Command.create({"name": "Fluent", "level_progress": 100})
                ],
            }
        )
        cls.quechua = skill_type.skill_ids
        cls.speaker, cls.former_speaker = cls.env["hr.employee"].create(
            [{"name": "Speaks Quechua"}, {"name": "Spoke Quechua"}]
        )
        cls.env["hr.employee.skill"].create(
            [
                {
                    "employee_id": employee.id,
                    "skill_id": cls.quechua.id,
                    "skill_level_id": skill_type.skill_level_ids.id,
                    "skill_type_id": skill_type.id,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                }
                for employee, valid_from, valid_to in (
                    (cls.speaker, date(2020, 1, 1), False),
                    (cls.former_speaker, date(2020, 1, 1), date(2021, 1, 1)),
                )
            ]
        )
        cls.slots = cls.env["planning.slot"].create(
            [
                {
                    "resource_id": employee.resource_id.id,
                    "start_datetime": datetime(2026, 1, 5, 8),
                    "end_datetime": datetime(2026, 1, 5, 17),
                }
                for employee in (cls.speaker, cls.former_speaker)
            ]
        )

    def test_searching_shifts_by_skill_skips_skills_no_longer_held(self):
        found = self.env["planning.slot"].search(
            [
                ("id", "in", self.slots.ids),
                ("employee_skill_ids", "ilike", self.quechua.name),
            ]
        )
        self.assertEqual(found.employee_id, self.speaker)

    def test_the_analysis_report_searches_the_same_way(self):
        self.env.flush_all()
        found = self.env["planning.analysis.report"].search(
            [
                ("employee_id", "in", (self.speaker | self.former_speaker).ids),
                ("employee_skill_ids", "ilike", self.quechua.name),
            ]
        )
        self.assertEqual(found.employee_id, self.speaker)

    def test_the_gantt_offers_only_resources_holding_the_skill(self):
        expanded = (
            self.env["planning.slot"]
            .with_context(planning_expand_resource=True)
            ._group_expand_resource_id(
                self.env["resource.resource"],
                [
                    ("start_datetime", "<", datetime(2026, 1, 31)),
                    ("end_datetime", ">", datetime(2026, 1, 1)),
                    ("employee_skill_ids", "ilike", self.quechua.name),
                ],
            )
        )
        self.assertIn(self.speaker.resource_id, expanded)
        self.assertNotIn(self.former_speaker.resource_id, expanded)
