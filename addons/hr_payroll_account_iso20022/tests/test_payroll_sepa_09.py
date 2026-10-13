import base64

from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import test_xsd

from odoo.addons.hr_payroll_account_iso20022.tests.test_payroll_sepa import (
    TestPayrollSEPACreditTransferCommon,
)


@tagged("post_install", "-at_install")
class TestPayrollSEPANewCreditTransferXmlValidity(TestPayrollSEPACreditTransferCommon):
    @test_xsd(path="account_iso20022/schemas/pain.001.001.09.xsd")
    def test_hr_payroll_account_iso20022_09(self):
        self.bank_journal.sepa_pain_version = "pain.001.001.09"
        self.payslip_run.generate_payslips(employee_ids=[self.hr_employee_john.id])
        self.payslip_run.action_validate()
        file = (
            self.env["wizard.hr.payslip.export.payment.file"]
            .create(
                {
                    "payslip_ids": self.payslip_run.slip_ids.ids,
                    "payslip_run_id": self.payslip_run.id,
                    "export_format": "sepa",
                    "journal_id": self.bank_journal.id,
                }
            )
            ._create_sepa_binary()
        )

        self.assertTrue(file, "SEPA payment has not been created!")

        sct_doc = etree.fromstring(base64.b64decode(file))

        namespaces = {"ns": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"}
        uetr_text = sct_doc.findtext(
            ".//ns:CdtTrfTxInf/ns:PmtId/ns:UETR", namespaces=namespaces
        )
        self.assertEqual(uetr_text, self.payslip_run.slip_ids.iso20022_uetr)
        payments = self.payslip_run.slip_ids._acquire_iso20022_payments_data(
            self.bank_journal
        )
        self.assertTrue(payments)
        self.assertTrue(
            all(payment["iso20022_uetr"] == uetr_text for payment in payments)
        )
        self.assertEqual(self.payslip_run.slip_ids.iso20022_uetr, uetr_text)
        return sct_doc
