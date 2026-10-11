from datetime import date, datetime

from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install", "work_entry_planning")
class TestWorkEntryPlanning(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Tom Clauz",
                "wage": 3500,
                "work_entry_source": "planning",
                "date_version": "2020-01-01",
                "contract_date_start": "2020-01-01",
            }
        )
        cls.contract = cls.employee.version_id

    def test_basic_generation(self):
        planning_slot_vals = []
        for i in range(1, 31):
            new_date = datetime(2021, 9, i, 13, 0, 0)
            if new_date.weekday() >= 5:
                continue
            planning_slot_vals.append(
                {
                    "resource_id": self.employee.resource_id.id,
                    "start_datetime": new_date,
                    "end_datetime": new_date.replace(hour=17),
                }
            )
        slots = self.env["planning.slot"].create(planning_slot_vals)
        slots.action_planning_publish_and_send()
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertFalse(work_entries)
        self.contract.generate_work_entries(date(2021, 9, 1), date(2021, 9, 30))

        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(len(slots), len(work_entries))
        self.assertTrue(all(hwe.planning_slot_id for hwe in work_entries))

    def test_duplicate_slot(self):
        slots = self.env["planning.slot"].create(
            [
                {
                    "resource_id": self.employee.resource_id.id,
                    "start_datetime": datetime(2021, 9, 14, 13, 0, 0),
                    "end_datetime": datetime(2021, 9, 14, 17, 0, 0),
                },
                {
                    "resource_id": self.employee.resource_id.id,
                    "start_datetime": datetime(2021, 9, 14, 13, 0, 0),
                    "end_datetime": datetime(2021, 9, 14, 17, 0, 0),
                },
                {
                    "resource_id": self.employee.resource_id.id,
                    "start_datetime": datetime(2021, 9, 15, 13, 0, 0),
                    "end_datetime": datetime(2021, 9, 15, 17, 0, 0),
                },
                {
                    "resource_id": self.employee.resource_id.id,
                    "start_datetime": datetime(2021, 9, 15, 16, 0, 0),
                    "end_datetime": datetime(2021, 9, 15, 19, 0, 0),
                },
                {
                    "resource_id": self.employee.resource_id.id,
                    "start_datetime": datetime(2021, 9, 16, 13, 0, 0),
                    "end_datetime": datetime(2021, 9, 16, 17, 0, 0),
                },
                {
                    "resource_id": self.employee.resource_id.id,
                    "start_datetime": datetime(2021, 9, 16, 17, 0, 0),
                    "end_datetime": datetime(2021, 9, 16, 19, 0, 0),
                },
            ]
        )
        slots.action_planning_publish_and_send()
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertFalse(work_entries)

        self.contract.generate_work_entries(date(2021, 9, 1), date(2021, 9, 30))
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(len(work_entries), len(slots) / 2)
        self.assertEqual(
            len(work_entries.mapped("planning_slot_id")), len(slots.ids) / 2
        )

    def test_slot_within_period(self):
        boundaries_slots = self.env["planning.slot"].create(
            [
                {
                    "resource_id": self.employee.resource_id.id,
                    "start_datetime": datetime(2021, 9, 1, 14, 0, 0),
                    "end_datetime": datetime(2021, 9, 1, 17, 0, 0),
                },
                {
                    "resource_id": self.employee.resource_id.id,
                    "start_datetime": datetime(2021, 9, 30, 14, 0, 0),
                    "end_datetime": datetime(2021, 9, 30, 17, 0, 0),
                },
            ]
        )
        boundaries_slots.action_planning_publish_and_send()
        self.contract.generate_work_entries(date(2021, 9, 1), date(2021, 9, 30))
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(len(work_entries), len(boundaries_slots))

        inner_slot = self.env["planning.slot"].create(
            {
                "resource_id": self.employee.resource_id.id,
                "start_datetime": datetime(2021, 9, 14, 14, 0, 0),
                "end_datetime": datetime(2021, 9, 14, 17, 0, 0),
            }
        )
        inner_slot.action_send()
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(len(boundaries_slots) + len(inner_slot), len(work_entries))

    def test_publish_unpublish(self):
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.employee.resource_id.id,
                "start_datetime": datetime(2021, 9, 14, 14, 0, 0),
                "end_datetime": datetime(2021, 9, 14, 17, 0, 0),
            }
        )
        self.contract.write(
            {
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        slot.action_send()
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertTrue(work_entries)
        slot.action_unpublish()
        self.assertFalse(work_entries.active)
        slot.action_send()
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertTrue(work_entries)
        slot.unlink()
        self.assertFalse(work_entries.active)

    def test_work_entry_uses_slot_duration(self):
        slot = self.env["planning.slot"].create(
            {
                "resource_id": self.employee.resource_id.id,
                "start_datetime": datetime(2021, 9, 6, 0, 0, 0),
                "end_datetime": datetime(2021, 9, 10, 23, 59, 59),
                "allocated_hours": 38,
            }
        )
        slot.action_send()
        self.contract.generate_work_entries(date(2021, 9, 1), date(2021, 9, 30))
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertTrue(work_entries)
        self.assertEqual(sum(work_entries.mapped("duration")), slot.allocated_hours)

    def test_invalid_contract(self):
        self.contract.write(
            {
                "work_entry_source": "calendar",
            }
        )
        self.env["planning.slot"].create(
            {
                "resource_id": self.employee.resource_id.id,
                "start_datetime": datetime(2021, 9, 14, 14, 0, 0),
                "end_datetime": datetime(2021, 9, 14, 17, 0, 0),
                "state": "2_published",
            }
        )
        self.contract.generate_work_entries(date(2021, 9, 1), date(2021, 9, 30))
        work_entries = self.env["hr.work.entry"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertFalse(any(hwe.planning_slot_id for hwe in work_entries))

    def test_create_work_entries(self):
        self.contract.write(
            {
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        employee2 = self.env["hr.employee"].create(
            {
                "name": "Santa Cruise",
                "wage": 5300,
                "work_entry_source": "planning",
                "date_version": "2020-01-01",
                "contract_date_start": "2020-01-01",
                "date_generated_from": datetime(2021, 9, 1, 0, 0, 0),
                "date_generated_to": datetime(2021, 9, 30, 23, 59, 59),
            }
        )
        planning_slots = self.env["planning.slot"].create(
            [
                {
                    "resource_id": self.employee.resource_id.id,
                    "start_datetime": datetime(2021, 9, 14, 14, 0, 0),
                    "end_datetime": datetime(2021, 9, 14, 17, 0, 0),
                },
                {
                    "resource_id": employee2.resource_id.id,
                    "start_datetime": datetime(2021, 9, 15, 14, 0, 0),
                    "end_datetime": datetime(2021, 9, 15, 17, 0, 0),
                },
            ]
        )
        self.env["hr.work.entry"].create(
            {
                "name": "Mission Impossible: Distribute Gifts",
                "employee_id": employee2.id,
                "version_id": employee2.version_id.id,
                "date": date(2021, 9, 15),
                "duration": 3,
            }
        )
        planning_slots._create_work_entries()
