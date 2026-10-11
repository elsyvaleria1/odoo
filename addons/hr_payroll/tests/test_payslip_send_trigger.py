from datetime import date

from odoo import tests

from .common import TestPayslipBase


@tests.tagged("post_install", "-at_install")
class TestPayslipSendTrigger(TestPayslipBase):
    """When a validated payslip gets queued for the PDF cron.

    The cron is what mails the payslip: `_generate_pdf` creates the attachment and
    then sends the payslip template to every employee in the batch. So the trigger
    stored under `hr_payroll.payslip_generate_and_send_trigger` decides when
    employees receive their payslip, not merely when a PDF exists.

    `on_confirmed` queues on validation, `on_paid` queues when the payslip is marked
    as paid, and `never` queues at neither point -- printing stays manual through the
    Print menu. An absent parameter must behave exactly like `on_confirmed`, which is
    what the module did before the setting existed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.second_emp = cls.env["hr.employee"].create(
            {
                "name": "Second",
                "date_version": date(2018, 1, 1),
                "contract_date_start": date(2018, 1, 1),
                "wage": 3000.0,
                "structure_type_id": cls.structure_type.id,
            }
        )

    def setUp(self):
        super().setUp()
        self.payslip_richard = self._new_payslip(self.richard_emp)
        self.payslip_second = self._new_payslip(self.second_emp)

    def _new_payslip(self, employee):
        return self.env["hr.payslip"].create(
            {
                "name": f"Payslip {employee.name}",
                "employee_id": employee.id,
                "version_id": employee.version_id.id,
                "date_from": date(2025, 10, 1),
                "date_to": date(2025, 10, 31),
            }
        )

    def _set_trigger(self, value):
        self.env["ir.config_parameter"].sudo().set_param(
            "hr_payroll.payslip_generate_and_send_trigger", value
        )

    def _validate(self, payslips):
        payslips.with_context(payslip_generate_pdf=True).action_validate()

    def test_on_confirmed_queues_on_validation(self):
        self._set_trigger("on_confirmed")
        payslips = self.payslip_richard | self.payslip_second
        self._validate(payslips)
        self.assertTrue(
            all(payslips.mapped("queued_for_pdf")),
            "on_confirmed: validating must queue every payslip for the cron",
        )

    def test_on_paid_does_not_queue_on_validation(self):
        self._set_trigger("on_paid")
        payslips = self.payslip_richard | self.payslip_second
        self._validate(payslips)
        self.assertFalse(
            any(payslips.mapped("queued_for_pdf")),
            "on_paid: validating must not queue anything yet",
        )
        payslips.action_payslip_paid()
        self.assertTrue(
            all(payslips.mapped("queued_for_pdf")),
            "on_paid: marking as paid must queue every payslip",
        )

    def test_never_queues_at_neither_step(self):
        self._set_trigger("never")
        payslips = self.payslip_richard | self.payslip_second
        self._validate(payslips)
        self.assertFalse(
            any(payslips.mapped("queued_for_pdf")),
            "never: validating must not queue anything",
        )
        payslips.action_payslip_paid()
        self.assertFalse(
            any(payslips.mapped("queued_for_pdf")),
            "never: marking as paid must not queue anything either",
        )

    def test_on_confirmed_does_not_queue_again_on_payment(self):
        self._set_trigger("on_confirmed")
        payslips = self.payslip_richard | self.payslip_second
        self._validate(payslips)
        payslips.write({"queued_for_pdf": False})
        payslips.action_payslip_paid()
        self.assertFalse(
            any(payslips.mapped("queued_for_pdf")),
            "on_confirmed: payment must not queue a second round of PDFs",
        )

    def test_absent_parameter_behaves_as_on_confirmed(self):
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", "hr_payroll.payslip_generate_and_send_trigger")]
        ).unlink()
        self._validate(self.payslip_richard)
        self.assertTrue(
            self.payslip_richard.queued_for_pdf,
            "absent parameter: validating must queue, as it did before the setting",
        )

    def test_single_payslip_is_queued_not_generated_inline(self):
        self._set_trigger("on_confirmed")
        self._validate(self.payslip_richard)
        self.assertTrue(
            self.payslip_richard.queued_for_pdf,
            "a single payslip must be queued, not generated inline",
        )
        self.assertFalse(
            self.env["ir.attachment"].search(
                [
                    ("res_model", "=", "hr.payslip"),
                    ("res_id", "=", self.payslip_richard.id),
                ]
            ),
            "a single payslip must not have its PDF built during validation",
        )
