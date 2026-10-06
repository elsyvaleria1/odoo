from lxml import etree

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSaftImportTree(TransactionCase):
    def test_generic_import_keeps_account_and_customer_identifiers(self):
        self.env.company.country_id = self.env.ref("base.be")
        wizard = self.env["wizard.account.move.import.saft"].new({})
        source = b'<AuditFile xmlns="urn:StandardAuditFile-Taxation-Financial:Test"><AccountID>source</AccountID><StandardAccountID>standard</StandardAccountID><CustomerID>N/A</CustomerID></AuditFile>'
        first = wizard._prepare_import_tree(source)
        second = wizard._prepare_import_tree(source)
        self.assertIsNot(first, second)
        self.assertEqual(etree.tostring(first), source)
        self.assertEqual(etree.tostring(second), source)
