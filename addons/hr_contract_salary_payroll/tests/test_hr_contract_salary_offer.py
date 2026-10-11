from datetime import date
from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo.tests import Form, TransactionCase

from odoo.addons.hr_contract_salary.utils.hr_version import (
    HR_VERSION_CTX_KEY,
    hr_version_context,
)


class TestHrContractSalaryOffer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.offer_calendar = cls.env["resource.calendar"].create(
            {
                "name": "Offer Calendar",
                "hours_per_week": 40,
            }
        )
        cls.version_calendar = cls.env[
            "resource.calendar"
        ].create(
            {
                "name": "Version Calendar",
                "hours_per_day": 7.6,
                "hours_per_week": 38,
                "full_time_required_hours": 38,
            }
        )

        cls.struct_type = cls.env["hr.payroll.structure.type"].create(
            {"name": "Regular"}
        )
        cls.structure = cls.env["hr.payroll.structure"].create(
            {
                "name": "Regular structure",
                "type_id": cls.struct_type.id,
            }
        )
        cls.struct_type.default_struct_id = cls.structure

        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Tom Ato",
                "wage": 2000,
                "structure_type_id": cls.struct_type.id,
                "contract_date_start": date.today(),
            }
        )
        cls.version = cls.employee.version_ids[0]
        cls.version_ctx = {
            "salary_simulation": True,
            "tracking_disable": True,
            HR_VERSION_CTX_KEY: True,
        }

    def test_a_generated_offer_takes_the_employee_monthly_wage_as_its_default(self):
        action = self.employee.action_generate_offer()
        expected = self.version._get_gross_from_employer_costs(
            self.version.final_yearly_costs
        )
        self.assertTrue(expected)
        self.assertEqual(action["context"].get("default_monthly_wage"), expected)
        Offer = type(self.env["hr.contract.salary.offer"])
        get_version = Offer._acquire_version
        calls = []

        def counted(offer, **kwargs):
            calls.append(offer.id)
            return get_version(offer, **kwargs)

        with patch.object(Offer, "_acquire_version", counted):
            offer_form = Form(
                self.env["hr.contract.salary.offer"].with_context(**action["context"])
            )
        self.assertAlmostEqual(offer_form.monthly_wage, expected, places=2)
        self.assertEqual(len(calls), 1)

    def test_version_calendar_priority(self):
        offer = (
            self.env["hr.contract.salary.offer"]
            .create(
                {
                    "employee_id": self.employee.id,
                    "structure_id": self.structure.id,
                    "monthly_wage": 2000,
                    "resource_calendar_id": self.offer_calendar.id,
                }
            )
            .with_context(**self.version_ctx)
        )

        self.version.resource_calendar_id = False
        offer._compute_salary()
        version = offer._acquire_version()
        self.assertEqual(version.resource_calendar_id, self.offer_calendar)
        self.assertAlmostEqual(
            offer.gross_wage, 2000.0, places=2
        )

    def test_an_unmapped_simulation_schedule_falls_back_to_full_time(self):
        original_calendar = self.version.resource_calendar_id
        for hostile in ("70", "abc"):
            with hr_version_context(
                self.version.with_context(simulation_working_schedule=hostile)
            ) as version:
                payslip = version._generate_salary_simulation_payslip()
                self.assertTrue(
                    payslip.version_id.resource_calendar_id,
                    f"schedule {hostile!r} must not blank the calendar",
                )
                self.assertTrue(payslip.env.context.get("salary_simulation_full_time"))
                self.assertAlmostEqual(
                    payslip.version_id.wage_on_signature,
                    self.version.wage_on_signature,
                    places=2,
                )
        self.assertEqual(self.version.resource_calendar_id, original_calendar)

    def test_part_time_simulation_working_schedule_branches(self):
        company_calendar = self.env["resource.calendar"].create(
            {
                "name": "Full Time Calendar (10 non-lunch lines)",
                "company_id": self.employee.company_id.id,
                "hours_per_week": 40,
                "attendance_ids": [
                    (
                        0,
                        0,
                        {
                            "name": f"Day {day} {period}",
                            "dayofweek": str(day),
                            "hour_from": 8.0 if period == "morning" else 13.0,
                            "hour_to": 12.0 if period == "morning" else 17.0,
                            "day_period": period,
                        },
                    )
                    for day in range(5)
                    for period in ("morning", "afternoon")
                ],
            }
        )
        self.employee.company_id.resource_calendar_id = company_calendar
        self.version.wage_on_signature = 2000
        self.version.wage = 2000

        expected_by_schedule = {
            "80": (False, 8),
            "60": (False, 6),
            "50": (False, 5),
            "40": (False, 4),
            "20": (False, 2),
        }
        for schedule, (needs_two_weeks, remaining) in expected_by_schedule.items():
            with hr_version_context(
                self.version.with_context(simulation_working_schedule=schedule)
            ) as version:
                payslip = version._generate_salary_simulation_payslip()
                new_calendar = payslip.version_id.resource_calendar_id
                self.assertEqual(
                    new_calendar.two_weeks_calendar,
                    needs_two_weeks,
                    f"schedule {schedule} should leave two_weeks_calendar={needs_two_weeks}",
                )
                self.assertEqual(
                    len(
                        new_calendar.attendance_ids.filtered(
                            lambda a: a.day_period != "lunch"
                        )
                    ),
                    remaining,
                    f"schedule {schedule} should leave {remaining} non-lunch attendance lines",
                )
                self.assertFalse(payslip.env.context.get("salary_simulation_full_time"))
                self.assertAlmostEqual(
                    payslip.version_id.wage_on_signature,
                    2000 * int(schedule) / 100.0,
                    places=2,
                )
                self.assertAlmostEqual(
                    payslip.version_id.wage,
                    2000 * int(schedule) / 100.0,
                    places=2,
                )

        with hr_version_context(
            self.version.with_context(simulation_working_schedule="90")
        ) as version:
            payslip = version._generate_salary_simulation_payslip()
            self.assertTrue(payslip.version_id.resource_calendar_id.two_weeks_calendar)
            self.assertFalse(payslip.env.context.get("salary_simulation_full_time"))
            self.assertAlmostEqual(
                payslip.version_id.wage_on_signature, 1800.0, places=2
            )

        with hr_version_context(self.version) as version:
            payslip = version._generate_salary_simulation_payslip()
            self.assertTrue(payslip.env.context.get("salary_simulation_full_time"))
            self.assertAlmostEqual(
                payslip.version_id.wage_on_signature, 2000.0, places=2
            )

    def test_an_employee_under_contract_can_be_offered_a_template(self):
        template = self.env["hr.version"].create(
            {
                "name": "Next contract",
                "structure_type_id": self.struct_type.id,
                "wage": 3000,
                "wage_on_signature": 3000,
            }
        )
        offer_form = Form(
            self.env["hr.contract.salary.offer"].with_context(
                **self.employee.action_generate_offer()["context"]
            )
        )
        offer_form.contract_template_id = template
        self.assertEqual(offer_form.contract_template_id, template)
        self.assertAlmostEqual(offer_form.monthly_wage, 3000, places=2)
        self.assertFalse(self.version.contract_date_end)
        self.assertFalse(template.employee_id)

    def test_a_new_offer_keeps_the_contract_template_picked_in_its_form(self):
        template = self.env["hr.version"].create(
            {
                "name": "Picked template",
                "structure_type_id": self.struct_type.id,
                "wage": 3000,
                "wage_on_signature": 3000,
            }
        )
        employee = self.env["hr.employee"].create(
            {
                "name": "Offer Employee",
                "wage": 2000,
                "structure_type_id": self.struct_type.id,
                "contract_date_start": date.today() - relativedelta(years=1),
                "contract_date_end": date.today(),
            }
        )
        offer_form = Form(
            self.env["hr.contract.salary.offer"].with_context(
                **employee.action_generate_offer()["context"]
            )
        )
        Offer = type(self.env["hr.contract.salary.offer"])
        get_version = Offer._acquire_version
        calls = []

        def counted(offer, **kwargs):
            calls.append(offer.id)
            return get_version(offer, **kwargs)

        with patch.object(Offer, "_acquire_version", counted):
            offer_form.contract_template_id = template
        self.assertEqual(offer_form.contract_template_id, template)
        self.assertEqual(offer_form.final_yearly_costs, template.final_yearly_costs)
        self.assertAlmostEqual(offer_form.monthly_wage, 3000, places=2)
        self.assertEqual(len(calls), 2)
