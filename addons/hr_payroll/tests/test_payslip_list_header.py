from odoo.tests import HttpCase, tagged

from .common import TestPayslipBase


@tagged("post_install", "-at_install")
class TestPayslipListHeader(TestPayslipBase, HttpCase):
    """The header buttons of the payslip list on a selection of mixed states.

    `action_validate` filters to `state == "draft"` and `action_payslip_paid`
    raises unless every payslip is confirmed, so the two buttons must not be
    governed by the same rule.
    """

    def test_header_buttons_follow_what_each_action_tolerates(self):
        self.user_admin = self.env.ref("base.user_admin")
        self.user_admin.company_ids |= self.company_us
        self.user_admin.write(
            {
                "company_id": self.env.company.id,
                "email": "mitchell.admin@example.com",
            }
        )
        self.richard_emp.version_ids[0].wage = 1234

        draftee, confirmee = (
            self.richard_emp.copy({"name": "Probe Draftee"}),
            self.richard_emp.copy({"name": "Probe Confirmee"}),
        )
        for employee in (draftee, confirmee):
            employee.version_ids[0].wage = 1234

        draft = self.env["hr.payslip"].create(
            {"name": "Header probe draft", "employee_id": draftee.id}
        )
        draft.compute_sheet()
        done = self.env["hr.payslip"].create(
            {"name": "Header probe confirmed", "employee_id": confirmee.id}
        )
        done.compute_sheet()
        done.action_payslip_done()
        self.assertEqual(draft.state, "draft")
        self.assertEqual(done.state, "validated")

        self.start_tour("/odoo", "hr_payroll_payslip_list_header_tour", login="admin")
