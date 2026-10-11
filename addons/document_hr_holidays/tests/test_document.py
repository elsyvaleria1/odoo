from datetime import date

from odoo.tests.common import tagged

from odoo.addons.document_hr.tests.test_document_hr_common import (
    TransactionCaseDocumentsHr,
)


@tagged("post_install", "-at_install", "test_document_bridge")
class TestCaseDocumentsBridgeHR(TransactionCaseDocumentsHr):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Employee (related to doc_user)",
                "user_id": cls.doc_user.id,
                "partner_id": cls.doc_user.partner_id.id,
            }
        )
        cls.leave_type = cls.env["hr.leave.type"].create(
            {"name": "Sick", "requires_allocation": False}
        )
        cls.leave = cls.env["hr.leave"].create(
            {
                "employee_id": cls.employee.id,
                "holiday_status_id": cls.leave_type.id,
                "request_date_from": date(2021, 11, 24),
                "request_date_to": date(2021, 11, 24),
            }
        )

    def test_leave_document_creation(self):
        attachment = self.env["ir.attachment"].create(
            {
                "datas": self.TEXT,
                "name": "fileText_test.txt",
                "mimetype": "text/plain",
                "res_model": self.leave._name,
                "res_id": self.leave.id,
            }
        )

        document = self.env["document.document"].search(
            [("attachment_id", "=", attachment.id)]
        )
        self.assertTrue(
            document.exists(),
            "There should be a new document created from the attachment",
        )
        self.assertFalse(document.owner_id)
        self.assertEqual(
            document.folder_id,
            self.employee.hr_employee_folder_id,
            "filed with the employee's other files, not at the employees root",
        )
        self.assertEqual(
            document.partner_id,
            self.employee.partner_id,
            "The partner_id should be the employee's address",
        )
        self.assertEqual(document.access_via_link, "none")
        self.assertEqual(document.access_internal, "none")
        self.assertTrue(document.is_access_via_link_hidden)

    def test_hr_leave_document_creation_permission_employee_only(self):
        self.check_document_creation_permission(self.leave)
