import io

from odoo.exceptions import RedirectWarning, UserError
from odoo.tests import tagged
from odoo.tools import file_open
from odoo.tools.pdf import OdooPdfFileReader, OdooPdfFileWriter

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestCamtInsidePdf(AccountTestInvoicingCommon):
    """A statement delivered as a PDF that carries its own CAMT.

    The same shape as a Factur-X invoice, which the bill importer has read
    since it existed: a human-readable document with the machine-readable one
    embedded in it. Banks deliver statements this way.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.env["account.journal"].create(
            {
                "name": "Bank 123456",
                "code": "BNK67",
                "type": "bank",
                "bank_acc_number": "123456",
                "currency_id": cls.env.ref("base.USD").id,
            }
        )
        with file_open(
            "account_bank_statement_import_camt/test_camt_file/test_camt.xml", "rb"
        ) as f:
            cls.camt = f.read()
        cls.pdf = cls._wrap_in_pdf(cls.camt)

    @classmethod
    def _wrap_in_pdf(cls, payload):
        with file_open("base/tests/minimal.pdf", "rb") as carrier:
            reader = OdooPdfFileReader(io.BytesIO(carrier.read()), strict=False)
        writer = OdooPdfFileWriter()
        writer.clone_reader_document_root(reader)
        writer.add_attachment("statement.xml", payload, subtype="text/xml")
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    def _import(self, raw, name, mimetype):
        attachment = self.env["ir.attachment"].create(
            {"mimetype": mimetype, "name": name, "raw": raw}
        )
        return self.bank_journal.create_document_from_attachment(attachment.ids)

    def _statements(self):
        return self.env["account.bank.statement"].search(
            [("company_id", "=", self.env.company.id)]
        )

    def test_the_bare_camt_still_imports(self):
        self._import(self.camt, "test_camt.xml", "application/xml")

        self.assertEqual(self._statements().balance_start, 8998.20)

    def test_a_camt_inside_a_pdf_imports(self):
        self._import(self.pdf, "statement.pdf", "application/pdf")

        statement = self._statements()
        self.assertTrue(
            statement,
            "the PDF carries a CAMT and nothing read it",
        )
        self.assertEqual(statement.balance_start, 8998.20)
        self.assertEqual(statement.balance_end_real, 2661.49)

    def test_a_pdf_carrying_nothing_still_reports_it_cannot_be_read(self):
        with file_open("base/tests/minimal.pdf", "rb") as carrier:
            empty_pdf = carrier.read()

        with self.assertRaises((UserError, RedirectWarning)):
            self._import(empty_pdf, "nothing.pdf", "application/pdf")
