from itertools import product

from odoo import Command
from odoo.fields import Domain
from odoo.tests import TransactionCase, new_test_user


class TestAllocationRequestDomain(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other_company = cls.env["res.company"].create(
            {"name": "Other allocation company"}
        )
        cls.employee = new_test_user(
            cls.env, login="allocation_domain_employee", groups="base.group_user"
        )
        cls.officer = new_test_user(
            cls.env,
            login="allocation_domain_officer",
            groups="hr_holidays.group_hr_holidays_user",
        )
        (cls.employee | cls.officer).write(
            {"company_ids": [Command.set((cls.company | cls.other_company).ids)]}
        )
        cls.leave_types = cls.env["hr.leave.type"].create(
            [
                {
                    "name": f"Domain type {company_id} {requires_allocation} {employee_requests}",
                    "company_id": company_id,
                    "requires_allocation": requires_allocation,
                    "employee_requests": employee_requests,
                }
                for company_id, requires_allocation, employee_requests in product(
                    (False, cls.company.id, cls.other_company.id),
                    (False, True),
                    (False, True),
                )
            ]
        )

    def test_employee_sees_requestable_allocated_types_in_allowed_companies(self):
        for companies in (self.company, self.company | self.other_company):
            owner = (
                self.env["hr.leave.type"]
                .with_user(self.employee)
                .with_context(allowed_company_ids=companies.ids)
            )
            domain = owner._get_allocation_request_domain()
            self.assertIsInstance(domain, Domain)
            expected = self.leave_types.filtered(
                lambda t, companies=companies: (
                    t.requires_allocation
                    and t.employee_requests
                    and (not t.company_id or t.company_id in companies)
                )
            )
            self.assertEqual(self.leave_types.filtered_domain(domain), expected)

    def test_officer_can_allocate_types_employees_cannot_request(self):
        owner = (
            self.env["hr.leave.type"]
            .with_user(self.officer)
            .with_context(allowed_company_ids=self.company.ids)
        )
        expected = self.leave_types.filtered(
            lambda t: (
                t.requires_allocation
                and (not t.company_id or t.company_id == self.company)
            )
        )
        self.assertEqual(
            self.leave_types.filtered_domain(owner._get_allocation_request_domain()),
            expected,
        )
        self.assertTrue(expected.filtered(lambda t: not t.employee_requests))

    def test_both_field_hooks_use_the_callers_access_scope(self):
        for user, companies in product(
            (self.employee, self.officer),
            (self.company, self.company | self.other_company),
        ):
            for model in ("hr.leave.allocation", "wizard.hr.leave.allocation.create"):
                record = (
                    self.env[model]
                    .with_user(user)
                    .with_context(allowed_company_ids=companies.ids)
                )
                expected = record.env["hr.leave.type"]._get_allocation_request_domain()
                actual = record._domain_holiday_status_id()
                self.assertIsInstance(actual, Domain)
                self.assertEqual(
                    self.leave_types.filtered_domain(actual),
                    self.leave_types.filtered_domain(expected),
                )
