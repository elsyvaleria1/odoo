from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAccountBankStatementImportQIF(AccountTestInvoicingCommon):
    def test_qif_file_import(self):
        bank_journal = self.env["account.journal"].create(
            {
                "name": "bank QIF",
                "code": "BNK67",
                "type": "bank",
                "bank_acc_number": "123456",
                "currency_id": self.env.ref("base.USD").id,
            }
        )

        qif_file_path = "account_bank_statement_import_qif/static/qif/test_qif.qif"
        with file_open(qif_file_path, "rb") as qif_file:
            bank_journal.create_document_from_attachment(
                self.env["ir.attachment"]
                .create(
                    {
                        "mimetype": "application/text",
                        "name": "test_qif.qif",
                        "raw": qif_file.read(),
                    }
                )
                .ids
            )

        imported_statement = self.env["account.bank.statement"].search(
            [("company_id", "=", self.env.company.id)]
        )
        self.assertRecordValues(
            imported_statement,
            [
                {
                    "balance_start": 0.0,
                    "balance_end_real": -1896.09,
                }
            ],
        )
        self.assertRecordValues(
            imported_statement.line_ids.sorted("payment_ref"),
            [
                {"amount": -1000.00, "payment_ref": "Delta PC"},
                {"amount": -379.00, "payment_ref": "Epic Technologies"},
                {"amount": -421.35, "payment_ref": "SPRINGFIELD WATER UTILITY"},
                {"amount": -75.46, "payment_ref": "Walts Drugs"},
                {"amount": -20.28, "payment_ref": "YOUR LOCAL SUPERMARKET"},
            ],
        )

    def test_qif_with_a_latin1_payee_imports(self):
        """A payee or memo with an accent used to raise UnicodeDecodeError out
        of a bare `bytes.decode()`, which is most non-English QIF exports."""
        bank_journal = self.env["account.journal"].create(
            {
                "name": "bank QIF latin-1",
                "code": "BNK68",
                "type": "bank",
                "bank_acc_number": "654321",
                "currency_id": self.env.ref("base.USD").id,
            }
        )
        qif = (
            "!Type:Bank\nD8/12/13\nT-42.00\nPCafé Ñoño\nMRéglement août\n^\n"
        ).encode("latin-1")

        bank_journal.create_document_from_attachment(
            self.env["ir.attachment"]
            .create(
                {
                    "mimetype": "application/text",
                    "name": "latin1.qif",
                    "raw": qif,
                }
            )
            .ids
        )

        line = self.env["account.bank.statement.line"].search(
            [("journal_id", "=", bank_journal.id)]
        )
        self.assertEqual(line.payment_ref, "Café Ñoño: Réglement août")
