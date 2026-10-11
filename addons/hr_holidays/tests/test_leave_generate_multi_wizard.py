from datetime import date

from lxml import etree

from odoo.tests import tagged

from odoo.addons.hr_holidays.tests.common import TestHrHolidaysCommon


@tagged("multi_wizard")
class TestLeaveGenerateMultiWizard(TestHrHolidaysCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.allocated_type = cls.env["hr.leave.type"].create(
            {
                "name": "Batch Time Off",
                "requires_allocation": True,
                "allocation_validation_type": "no_validation",
                "leave_validation_type": "no_validation",
                "company_id": cls.company.id,
            }
        )
        cls.covered = cls.employee_emp
        cls.uncovered = cls.env["hr.employee"].create(
            {"name": "No Allocation Employee", "company_id": cls.company.id}
        )
        cls.env["hr.leave.allocation"].create(
            {
                "name": "Days for the covered one",
                "employee_id": cls.covered.id,
                "holiday_status_id": cls.allocated_type.id,
                "number_of_days": 20,
                "date_from": date(2026, 1, 1),
            }
        )

    def _wizard(self, **values):
        return self.env["wizard.hr.leave.create"].create(
            {
                "name": "Company shutdown",
                "holiday_status_id": self.allocated_type.id,
                "allocation_mode": "employee",
                "employee_ids": [(6, 0, (self.covered | self.uncovered).ids)],
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 10),
                **values,
            }
        )

    def test_one_employee_without_allocation_does_not_sink_the_batch(self):
        wizard = self._wizard()
        action = wizard.action_generate_time_off()

        leaves = self.env["hr.leave"].search(action["domain"])
        self.assertEqual(
            leaves.employee_id,
            self.covered,
            "the covered employee should have been given the time off",
        )
        self.assertFalse(
            self.env["hr.leave"].search(
                [
                    ("employee_id", "=", self.uncovered.id),
                    ("holiday_status_id", "=", self.allocated_type.id),
                ]
            ),
            "the employee with no allocation should not end up with a leave",
        )

    def test_allocated_types_are_selectable(self):
        arch = etree.fromstring(
            self.env.ref("hr_holidays.hr_leave_generate_multi_wizard_view_form").arch
        )
        field = arch.xpath("//field[@name='holiday_status_id']")[0]
        self.assertNotIn(
            "requires_allocation",
            field.get("domain") or "",
            "types requiring an allocation must not be filtered out any more",
        )

    def test_no_employee_selected_means_everyone(self):
        arch = etree.fromstring(
            self.env.ref("hr_holidays.hr_leave_generate_multi_wizard_view_form").arch
        )
        field = arch.xpath("//field[@name='employee_ids']")[0]
        self.assertFalse(
            field.get("required"),
            "the employee list must be optional for 'Everyone' to be reachable",
        )
        wizard = self._wizard(employee_ids=[(5, 0, 0)])
        action = wizard.action_generate_time_off()
        leaves = self.env["hr.leave"].search(action["domain"])
        self.assertIn(
            self.covered,
            leaves.employee_id,
            "an empty selection should have reached the whole company",
        )

    def test_a_batch_of_only_uncovered_employees_still_reports(self):
        wizard = self._wizard(employee_ids=[(6, 0, self.uncovered.ids)])
        action = wizard.action_generate_time_off()
        self.assertFalse(self.env["hr.leave"].search(action["domain"]))

    def _typed_wizard(self, request_unit, **values):
        leave_type = self.env["hr.leave.type"].create(
            {
                "name": f"Batch {request_unit}",
                "requires_allocation": False,
                "leave_validation_type": "no_validation",
                "request_unit": request_unit,
                "company_id": self.company.id,
            }
        )
        return self.env["wizard.hr.leave.create"].create(
            {
                "name": f"Batch of {request_unit}",
                "holiday_status_id": leave_type.id,
                "allocation_mode": "employee",
                "employee_ids": [(6, 0, self.covered.ids)],
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 10),
                **values,
            }
        )

    def test_hourly_type_keeps_the_hours_asked_for(self):
        wizard = self._typed_wizard("hour", hour_from=9.0, hour_to=12.0)
        action = wizard.action_generate_time_off()
        leave = self.env["hr.leave"].search(action["domain"])

        self.assertEqual(len(leave), 1)
        self.assertEqual(leave.request_hour_from, 9.0)
        self.assertEqual(leave.request_hour_to, 12.0)
        self.assertEqual(
            leave.number_of_hours,
            3.0,
            "a 09:00-12:00 batch request should last three hours, not a full day",
        )

    def test_half_day_type_keeps_the_period_asked_for(self):
        wizard = self._typed_wizard(
            "half_day", date_from_period="pm", date_to_period="pm"
        )
        action = wizard.action_generate_time_off()
        leave = self.env["hr.leave"].search(action["domain"])

        self.assertEqual(len(leave), 1)
        self.assertEqual(leave.request_date_from_period, "pm")
        self.assertEqual(
            leave.number_of_days,
            0.5,
            "an afternoon batch request should last half a day",
        )

    def test_employee_selection_modes_in_both_wizards(self):
        tag = self.env["res.partner.tag"].create({"name": "Batch selection"})
        (self.covered | self.employee_external).write({"tag_ids": [(4, tag.id)]})
        self.uncovered.department_id = self.rd_dept
        employees = self.env["hr.employee"].search(
            [("company_id", "=", self.company.id)]
        )
        for model in ("wizard.hr.leave.create", "wizard.hr.leave.allocation.create"):
            for mode, values, expected in (
                (
                    "employee",
                    {"employee_ids": [(6, 0, self.covered.ids)]},
                    self.covered,
                ),
                ("employee", {"employee_ids": [(5, 0, 0)]}, employees),
                ("company", {}, employees),
                (
                    "department",
                    {"department_id": self.rd_dept.id},
                    self.rd_dept.member_ids,
                ),
                ("category", {"tag_id": tag.id}, self.covered),
            ):
                with self.subTest(model=model, mode=mode, values=values):
                    wizard = (
                        self.env[model]
                        .with_context(
                            allowed_company_ids=[self.company.id],
                        )
                        .create(
                            {
                                "holiday_status_id": self.allocated_type.id,
                                "company_id": self.company.id,
                                "date_from": date(2026, 6, 10),
                                "date_to": date(2026, 6, 10),
                                "allocation_mode": mode,
                                **values,
                            }
                        )
                    )
                    self.assertEqual(
                        set(wizard._get_employees_from_allocation_mode().ids),
                        set(expected.ids),
                    )

    def test_employee_selection_domain_keeps_responsible_scope(self):
        for model in ("wizard.hr.leave.create", "wizard.hr.leave.allocation.create"):
            with self.subTest(model=model):
                wizard = (
                    self.env[model]
                    .with_user(self.user_responsible)
                    .with_context(
                        allowed_company_ids=[self.company.id],
                    )
                )
                employees = self.env["hr.employee"].search(
                    wizard._domain_employee_ids()
                )
                self.assertIn(self.covered, employees)
                self.assertIn(self.employee_responsible, employees)
                self.assertNotIn(self.uncovered, employees)
                self.assertNotIn(self.employee_external, employees)

    def test_employee_selections_persist_independently(self):
        values = {
            "holiday_status_id": self.allocated_type.id,
            "company_id": self.company.id,
            "date_from": date(2026, 6, 10),
            "date_to": date(2026, 6, 10),
        }
        leave = self.env["wizard.hr.leave.create"].create(
            {
                **values,
                "employee_ids": [(6, 0, self.covered.ids)],
            }
        )
        allocation = self.env["wizard.hr.leave.allocation.create"].create(
            {
                **values,
                "employee_ids": [(6, 0, self.uncovered.ids)],
            }
        )
        leave.flush_recordset()
        allocation.flush_recordset()
        leave.invalidate_recordset()
        allocation.invalidate_recordset()
        self.assertEqual(leave.employee_ids, self.covered)
        self.assertEqual(allocation.employee_ids, self.uncovered)
        self.assertNotEqual(
            leave._fields["employee_ids"].relation,
            allocation._fields["employee_ids"].relation,
        )
