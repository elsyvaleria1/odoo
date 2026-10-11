from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo.fields import Date
from odoo.tests.common import tagged

from odoo.addons.document.tests.test_document_multipage import single_page_pdf
from odoo.addons.document_hr.tests.test_document_hr_common import (
    TransactionCaseDocumentsHr,
)
from odoo.addons.hr_payroll.tests.common import TestPayslipBase


@tagged("test_document_bridge")
class TestCaseDocumentsBridgeHR(TestPayslipBase, TransactionCaseDocumentsHr):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env = cls.env(
            context=dict(cls.env.context, allowed_company_ids=cls.company_us.ids)
        )
        cls.env.user.company_id = cls.env.company.id

        cls.payroll_manager = cls.env["res.users"].create(
            {
                "name": "Hr payroll manager test",
                "login": "hr_payroll_manager_test",
                "email": "hr_payroll_manager_test@yourcompany.com",
                "group_ids": [
                    (6, 0, [cls.env.ref("hr_payroll.group_hr_payroll_user").id])
                ],
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Employee (related to doc_user_2)",
                "user_id": cls.doc_user_2.id,
                "partner_id": cls.doc_user_2.partner_id.id,
            }
        )
        cls.richard_emp.user_id = cls.doc_user
        cls.contract = cls.richard_emp.version_ids[0]
        cls.payslip = cls.env["hr.payslip"].create(
            {
                "name": "Payslip of Richard",
                "employee_id": cls.richard_emp.id,
                "version_id": cls.contract.id,
            }
        )

    def test_payslip_document_creation(self):
        self.payslip.compute_sheet()
        self.payslip.with_context(
            payslip_generate_pdf=True, payslip_generate_pdf_direct=True
        ).action_payslip_done()

        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", self.payslip._name), ("res_id", "=", self.payslip.id)]
        )
        self.assertTrue(
            attachment, "Validating a payslip should have created an attachment"
        )

        document = self.env["document.document"].search(
            [("attachment_id", "=", attachment.id)]
        )
        self.assertTrue(
            document, "There should be a new document created from the attachment"
        )
        self.assertEqual(document.owner_id, self.richard_emp.user_id)
        self.assertEqual(
            document.partner_id,
            self.richard_emp.user_id.partner_id,
            "The document contact must be the user partner of the employee",
        )
        self.assertFalse(
            document.folder_id,
            "The document should have been created in the employee's My Drive",
        )
        self.assertEqual(document.access_via_link, "view")
        self.assertEqual(document.access_internal, "none")
        self.assertTrue(document.is_access_via_link_hidden)
        self.assertEqual(
            {a.partner_id: a.role for a in document.access_ids},
            {self.richard_emp.user_id.partner_id: "view"},
        )
        self.assertEqual(
            document.sudo().access_log_ids.partner_id,
            self.richard_emp.user_id.partner_id,
        )
        self.assertEqual(
            document.with_user(self.richard_emp.user_id).user_permission, "edit"
        )
        self.check_document_no_access(document, self.doc_user_2)
        self.check_document_no_access(document, self.document_manager)
        self.check_document_no_access(document, self.payroll_manager)

    def test_hr_payroll_employee_declaration_document_creation_simple(self):
        declaration = self.env["hr.payroll.employee.declaration"].create(
            {
                "res_model": "hr.payslip",
                "res_id": self.payslip.id,
                "employee_id": self.employee.id,
                "pdf_file": single_page_pdf,
                "pdf_filename": "Test Declaration.pdf",
                "pdf_to_post": True,
            }
        )
        self.assertEqual(
            declaration.state,
            "pdf_to_post",
            "Queueing a generated declaration should move it to 'pdf_to_post'",
        )

        with (
            patch.object(
                self.env["hr.payslip"].pool["hr.payslip"],
                "_get_posted_mail_template",
                lambda s: self.env.ref(
                    "document_hr_payroll.mail_template_new_declaration",
                    raise_if_not_found=False,
                ),
                create=True,
            ),
            patch.object(
                self.env["hr.payslip"].pool["hr.payslip"],
                "_get_posted_document_owner",
                lambda _s, employee: employee.user_id,
                create=True,
            ),
        ):
            declaration._post_pdf()

        document = declaration.document_id
        self.assertEqual(document.name, "Test Declaration.pdf")
        self.assertEqual(document.owner_id, self.employee.user_id)
        self.assertFalse(
            document.folder_id,
            "The document should have been created in the employee's My Drive",
        )
        self.assertFalse(document.access_ids, "the owner is granted nothing")
        self.assertEqual(document.access_via_link, "view")
        self.assertEqual(document.access_internal, "none")
        self.assertTrue(document.is_access_via_link_hidden)
        self.check_document_no_access(document, self.doc_user)
        self.check_document_no_access(document, self.document_manager)
        self.check_document_no_access(document, self.payroll_manager)

    def test_apply_payslip_documents_settings_revokes_demoted_payroll_user(self):
        folder = self.employees_folder
        company = self.env["res.company"].search(
            [("documents_employee_folder_id", "=", folder.id)]
        )
        folder.company_id = company.id
        group = self.env.ref("hr_payroll.group_hr_payroll_user")

        company._apply_payslip_documents_settings()
        self.assertEqual(
            folder.access_ids.filtered("group_id").mapped(
                lambda a: (a.group_id, a.role, a.cause, a.cause_ref)
            ),
            [(group, "edit", "module", f"res.company,{company.id}")],
        )
        self.assertFalse(
            folder.access_ids.filtered(
                lambda a: a.partner_id == self.payroll_manager.partner_id
            ),
            "nobody is written on the folder for being in the group",
        )
        outsider = self.payroll_manager.copy({"login": "payroll_other_company"})
        outsider.company_ids = self.env["res.company"].search(
            [("id", "!=", company.id)], limit=1
        )
        folder.invalidate_recordset()
        self.assertEqual(
            folder.with_user(outsider).user_permission,
            "none",
            "the grant is to payroll users of the root's company only",
        )
        self.payroll_manager.company_ids |= company
        folder.invalidate_recordset()
        self.assertEqual(folder.with_user(self.payroll_manager).user_permission, "edit")

        self.payroll_manager.group_ids = [(3, group.id)]
        folder.invalidate_recordset()
        self.assertEqual(
            folder.with_user(self.payroll_manager).user_permission,
            "none",
            "Demoted payroll user should lose access at once",
        )

    def test_the_payroll_grant_follows_the_root_and_its_company(self):
        company = self.env["res.company"].search(
            [("documents_employee_folder_id", "=", self.employees_folder.id)]
        )
        group = self.env.ref("hr_payroll.group_hr_payroll_user")
        old_root = company.documents_employee_folder_id
        new_root = self.env["document.document"].create(
            {"name": "New employees root", "type": "folder", "company_id": company.id}
        )
        company.documents_employee_folder_id = new_root
        grants = self.env["document.access"].search(
            [("cause_ref", "=", f"res.company,{company.id}")]
        )
        self.assertEqual(
            grants.mapped(lambda a: (a.document_id, a.group_id, a.company_id)),
            [(new_root, group, company)],
        )
        self.assertFalse(old_root.access_ids.filtered("group_id"))

    def test_apply_payslip_documents_settings_keeps_admin_tags(self):
        company = self.env.company
        custom_tag = self.env["document.tag"].create({"name": "Custom Payslip Tag"})
        company.documents_hr_payslips_tags = [(6, 0, custom_tag.ids)]
        company._apply_payslip_documents_settings()
        self.assertEqual(
            company.documents_hr_payslips_tags,
            custom_tag,
            "A re-apply run must leave the admin's tag configuration alone",
        )

        company.documents_hr_payslips_tags = [(5, 0, 0)]
        company._apply_payslip_documents_settings()
        self.assertEqual(
            company.documents_hr_payslips_tags,
            self.env.ref("document_hr_payroll.documents_tag_payslips"),
            "A company with no tags still gets the default payslip tag",
        )

    def test_hr_payroll_documents_employee_without_user(self):
        employee_partner = self.env["res.partner"].create({"name": "partner"})
        self.richard_emp.user_id = False
        self.richard_emp.partner_id = employee_partner.id

        self.payslip.compute_sheet()
        self.payslip.with_context(
            payslip_generate_pdf=True, payslip_generate_pdf_direct=True
        ).action_payslip_done()

        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", self.payslip._name), ("res_id", "=", self.payslip.id)]
        )
        self.assertTrue(
            attachment, "Validating a payslip should have created an attachment"
        )

        document = self.env["document.document"].search(
            [("attachment_id", "=", attachment.id)]
        )
        self.assertTrue(
            document, "There should be a new document created from the attachment"
        )
        self.assertFalse(document.owner_id)
        self.assertEqual(
            document.partner_id,
            self.richard_emp.partner_id,
            "The document contact must be the user partner of the employee",
        )
        self.assertEqual(
            document.folder_id,
            self.richard_emp.company_id.worker_payroll_folder_id,
            "The document should have been created in the company Workers Payroll folder",
        )
        self.assertEqual(document.access_via_link, "view")
        self.assertEqual(document.access_internal, "none")
        self.assertTrue(document.is_access_via_link_hidden)
        self.assertFalse(self.richard_emp.user_id)
        self.assertEqual(
            {a.partner_id: a.role for a in document.access_ids},
            {self.richard_emp.partner_id: "view"},
            "Only the employee's work contact should have access, in view",
        )
        self.check_document_no_access(document, self.doc_user_2)
        self.check_document_no_access(document, self.document_manager)
        self.assertEqual(
            document.with_user(self.payroll_manager).user_permission, "edit"
        )

    def test_payslip_document_creation_with_no_partner(self):
        self.richard_emp.user_id = False

        payslip = self.payslip
        payslip.compute_sheet()
        payslip.with_context(payslip_generate_pdf=True).action_payslip_done()
        self.assertTrue(
            payslip.queued_for_pdf,
            "Payslip should be queued for PDF generation when not generating directly.",
        )

        payslip.browse()._cron_generate_pdf()

        document = self.env["document.document"].search(
            [("res_model", "=", payslip._name), ("res_id", "=", payslip.id)]
        )
        self.assertTrue(document)
        self.assertEqual(document.partner_id, self.richard_emp.partner_id)

    def test_payslip_document_creation_with_several_payslips(self):
        contract_jul = self.jules_emp.create_version(
            {
                "date_version": Date.to_date("2018-01-01"),
                "contract_date_start": Date.to_date("2018-01-01"),
                "contract_date_end": Date.today() + relativedelta(years=2),
                "date_end": Date.today() + relativedelta(years=2),
                "name": "Contract for Jules",
                "wage": 5000.33,
                "structure_type_id": self.structure_type.id,
            }
        )

        payslip_jul = self.env["hr.payslip"].create(
            {
                "name": "Payslip of Jules",
                "employee_id": self.jules_emp.id,
                "version_id": contract_jul.id,
            }
        )
        payslip_ric = self.payslip
        payslips = payslip_jul + payslip_ric

        payslips.compute_sheet()
        payslips.with_context(payslip_generate_pdf=True).action_payslip_done()
        self.assertTrue(payslip_jul.queued_for_pdf)
        self.assertTrue(payslip_ric.queued_for_pdf)

        self.env["hr.payslip"]._cron_generate_pdf()

        documents = self.env["document.document"].search(
            [("res_model", "=", payslips._name), ("res_id", "in", payslips.ids)]
        )
        self.assertEqual(len(documents), 2)
