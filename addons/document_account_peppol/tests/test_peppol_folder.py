from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPeppolFolder(TransactionCase):
    def test_the_peppol_reception_folder_cannot_be_trashed_or_deleted(self):
        folder = self.env["document.document"].create(
            {"name": "Peppol inbox", "type": "folder"}
        )
        self.env.company.documents_account_peppol_folder_id = folder
        with self.assertRaises(UserError):
            folder.action_archive()
        with self.assertRaises(UserError):
            folder.unlink()
