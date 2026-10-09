from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.approval.tests.common import ApprovalCommon


@tagged("post_install", "-at_install")
class TestAdoptionOwner(ApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls._make_category(
            "Adoption", approvers=[(cls.approver_1, True, 10)]
        )
        cls.env["ir.access"].create(
            {
                "name": "approval.test.document: internal users update it",
                "model_id": cls.env["ir.model"]._get_id("approval.test.document"),
                "group_id": cls.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "ru",
            }
        )

    def _document_written_by(self, user):
        document = self.env["approval.test.document"].create(
            {"name": "Adopter", "test_category_id": self.category.id}
        )
        written = document.with_user(user)
        written.check_access("write")
        written.write({"description": "the writer may write this document"})
        return written

    def test_nobody_adopts_someone_elses_unlinked_draft(self):
        request = self._prepare_request(self.category, confirm=False)
        document = self._document_written_by(self.approver_2)

        with self.assertRaises(ValidationError):
            document.write({"approval_request_id": request.id})

        request.invalidate_recordset()
        self.assertFalse(request.res_model)
        self.assertFalse(request.res_id)
        self.assertFalse(document.with_env(self.env).approval_request_id)

    def test_the_owner_adopts_their_own_unlinked_draft(self):
        request = self._prepare_request(self.category, confirm=False)
        document = self._document_written_by(self.owner_user)

        document.write({"approval_request_id": request.id})

        self.assertEqual(
            (request.res_model, request.res_id), (document._name, document.id)
        )
        self.assertEqual(document.with_env(self.env).approval_request_id, request)
