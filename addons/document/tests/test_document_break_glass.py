from odoo.fields import Command
from odoo.tests import tagged

from .test_document_common import TransactionCaseDocuments


@tagged("post_install", "-at_install")
class TestOthersDrive(TransactionCaseDocuments):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.system_admin = cls.env["res.users"].create(
            {
                "login": "docs_system",
                "name": "Documents System Administrator",
                "group_ids": [
                    Command.link(cls.env.ref("document.group_documents_system").id)
                ],
            }
        )
        Document = cls.env["document.document"]
        cls.drive = Document.create(
            {
                "name": "Internal user's folder",
                "type": "folder",
                "owner_id": cls.internal_user.id,
            }
        )
        cls.in_drive = Document.create(
            {"name": "private.txt", "raw": b"x", "folder_id": cls.drive.id}
        )
        cls.company_doc = Document.create(
            {"name": "company.txt", "raw": b"y", "folder_id": cls.folder_a.id}
        )
        cls.own_drive = Document.create(
            {"name": "mine.txt", "raw": b"z", "owner_id": cls.system_admin.id}
        )
        cls.glass = cls.env["res.users.eligibility"].create(
            {
                "user_id": cls.system_admin.id,
                "group_id": cls.env.ref("base.group_break_glass").id,
                "max_hours": 4,
            }
        )

    def reads(self, document):
        return document.with_user(self.system_admin).has_access("read")

    def test_a_system_administrator_reaches_another_drive_only_through_break_glass(
        self,
    ):
        self.assertTrue(self.reads(self.company_doc))
        self.assertTrue(self.reads(self.own_drive))
        self.assertFalse(self.reads(self.drive))
        self.assertFalse(self.reads(self.in_drive))
        self.glass.with_user(self.system_admin).action_activate(1, "a lost payslip")
        self.env.invalidate_all()
        self.assertTrue(self.reads(self.in_drive))
        self.assertEqual(
            self.in_drive.with_user(self.system_admin).user_permission, "edit"
        )
        self.glass.with_user(self.system_admin).action_stop()
        self.env.invalidate_all()
        self.assertFalse(self.reads(self.in_drive))

    def test_a_grant_in_another_drive_still_reaches(self):
        self.in_drive.access_ids = [
            Command.create(
                {"partner_id": self.system_admin.partner_id.id, "role": "view"}
            )
        ]
        self.assertTrue(self.reads(self.in_drive))
        self.assertFalse(self.reads(self.drive))
