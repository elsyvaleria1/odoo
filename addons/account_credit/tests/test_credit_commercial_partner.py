from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Command
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCreditCommercialFields(TransactionCase):
    def test_credit_fields_excluded_from_commercial_sync(self):
        partner_model = self.env["res.partner"]
        commercial = partner_model._commercial_fields()
        synced = partner_model._synced_commercial_fields()
        for fname in (
            "credit_grade_id",
            "credit_exception",
            "credit_trusted_amount",
            "credit_document_ids",
            "credit_limit",
        ):
            self.assertNotIn(fname, commercial)
            self.assertNotIn(fname, synced)


@tagged("post_install", "-at_install")
class TestCreditRedirect(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder = cls.env["document.document"].create(
            {"name": "Redirect Credit Folder", "type": "folder"}
        )
        cls.env.company.credit_folder_id = cls.folder
        cls.commercial = cls.env["res.partner"].create({"name": "Redirect Commercial"})
        cls.child = cls.env["res.partner"].create(
            {
                "name": "Redirect Child",
                "parent_id": cls.commercial.id,
                "type": "invoice",
            }
        )
        cls.credit_type = cls.env["credit.grade"].create(
            {"name": "Redirect Credit Type"}
        )

    def test_child_credit_write_redirects_to_commercial(self):
        self.child.write({"credit_grade_id": self.credit_type.id})
        self.assertEqual(self.commercial.credit_grade_id, self.credit_type)
        self.assertEqual(
            self.child.credit_grade_id,
            self.credit_type,
            "a contact reads its company's credit standing",
        )

    def test_commercial_write_reaches_children(self):
        self.commercial.write(
            {
                "credit_grade_id": self.credit_type.id,
                "credit_exception": True,
            }
        )
        self.assertEqual(self.child.credit_grade_id, self.credit_type)
        self.assertTrue(self.child.credit_exception)

    def test_child_credit_clear_redirects_to_commercial(self):
        self.commercial.write({"credit_grade_id": self.credit_type.id})
        self.child.write({"credit_grade_id": False})
        self.assertFalse(self.child.credit_grade_id)
        self.assertFalse(self.commercial.credit_grade_id)

    def test_child_credit_falsy_scalar_redirects(self):
        self.commercial.write({"credit_exception": True})
        self.child.write({"credit_exception": False})
        self.assertFalse(self.commercial.credit_exception)
        self.assertFalse(self.child.credit_exception)

    def test_mixed_vals_split(self):
        self.child.write(
            {
                "credit_grade_id": self.credit_type.id,
                "phone_ids": [
                    Command.create({"number": "555-0100", "type": "landline"})
                ],
            }
        )
        self.assertEqual(self.commercial.credit_grade_id, self.credit_type)
        self.assertEqual(self.child._phone_get_number().number, "555-0100")
        self.assertEqual(self.child.credit_grade_id, self.credit_type)
        self.assertFalse(self.commercial.phone_ids)

    def test_create_child_with_credit_redirects(self):
        new_child = self.env["res.partner"].create(
            {
                "name": "Redirect New Child",
                "parent_id": self.commercial.id,
                "type": "invoice",
                "credit_grade_id": self.credit_type.id,
            }
        )
        self.assertEqual(self.commercial.credit_grade_id, self.credit_type)
        self.assertEqual(new_child.credit_grade_id, self.credit_type)

    def test_child_document_link_redirects_to_commercial(self):
        document = self.env["document.document"].create(
            {"name": "Redirect Doc", "folder_id": self.folder.id}
        )
        self.child.write({"credit_document_ids": [Command.link(document.id)]})
        self.assertIn(document, self.commercial.credit_document_ids)
        self.assertNotIn(document, self.child.credit_document_ids)

    def test_child_document_plain_id_list_redirects(self):
        doc_a = self.env["document.document"].create(
            {"name": "Plain Doc A", "folder_id": self.folder.id}
        )
        doc_b = self.env["document.document"].create(
            {"name": "Plain Doc B", "folder_id": self.folder.id}
        )
        self.child.write({"credit_document_ids": [doc_a.id, doc_b.id]})
        self.assertIn(doc_a, self.commercial.credit_document_ids)
        self.assertIn(doc_b, self.commercial.credit_document_ids)
        self.assertFalse(self.child.credit_document_ids)

    def test_child_document_set_is_additive_on_commercial(self):
        existing = self.env["document.document"].create(
            {"name": "Existing Doc", "folder_id": self.folder.id}
        )
        incoming = self.env["document.document"].create(
            {"name": "Incoming Doc", "folder_id": self.folder.id}
        )
        self.commercial.write({"credit_document_ids": [Command.link(existing.id)]})
        self.child.write({"credit_document_ids": [Command.set([incoming.id])]})
        self.assertIn(existing, self.commercial.credit_document_ids)
        self.assertIn(incoming, self.commercial.credit_document_ids)
        self.assertFalse(self.child.credit_document_ids)

    def test_child_document_clear_allowed(self):
        document = self.env["document.document"].create(
            {"name": "Clear Doc", "folder_id": self.folder.id}
        )
        self.commercial.write({"credit_document_ids": [Command.link(document.id)]})
        self.child.write({"credit_document_ids": [Command.clear()]})
        self.assertIn(document, self.commercial.credit_document_ids)
        self.assertFalse(self.child.credit_document_ids)

    def test_family_batch_write_no_duplicate_documents(self):
        (self.commercial | self.child).write(
            {
                "credit_document_ids": [
                    Command.create({"name": "Batch Doc", "folder_id": self.folder.id})
                ]
            }
        )
        created = self.env["document.document"].search([("name", "=", "Batch Doc")])
        self.assertEqual(len(created), 1)
        self.assertIn(created, self.commercial.credit_document_ids)
        self.assertFalse(self.child.credit_document_ids)

    def test_legal_hold_on_child_redirects_to_commercial(self):
        self.child.write({"credit_legal_hold": True})
        self.assertTrue(self.commercial.credit_legal_hold)
        self.assertTrue(self.child.credit_legal_hold)
        self.assertEqual(self.commercial.credit_status, "legal")

    def test_exception_on_legally_held_commercial_raises(self):
        self.child.write({"credit_legal_hold": True})
        with self.assertRaises(ValidationError):
            self.commercial.write({"credit_exception": True})


@tagged("post_install", "-at_install")
class TestCreditRedirectAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.commercial = cls.env["res.partner"].create({"name": "Access Commercial"})
        cls.child = cls.env["res.partner"].create(
            {
                "name": "Access Child",
                "parent_id": cls.commercial.id,
                "type": "invoice",
            }
        )
        cls.user_no_credit = cls.env["res.users"].create(
            {
                "name": "No Credit User",
                "login": "test_no_credit_user",
                "email": "test_no_credit_user@example.com",
                "group_ids": [
                    Command.link(cls.env.ref("base.group_user").id),
                    Command.link(cls.env.ref("base.group_partner_manager").id),
                ],
            }
        )

    def test_non_credit_user_creates_contact_under_company(self):
        contact = (
            self.env["res.partner"]
            .with_user(self.user_no_credit)
            .create(
                {
                    "name": "Plain Contact",
                    "parent_id": self.commercial.id,
                    "type": "contact",
                }
            )
        )
        self.assertEqual(contact.commercial_partner_id, self.commercial)

    def test_non_credit_user_cannot_smuggle_trusted_amount(self):
        with self.assertRaises(AccessError):
            self.child.with_user(self.user_no_credit).write(
                {"credit_trusted_amount": 100.0}
            )
