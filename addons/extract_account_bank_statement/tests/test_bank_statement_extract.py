import contextlib

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.extract.tools import FREE, BaseExtractor
from odoo.addons.extract.tools import extractors as registry


class _Stub(BaseExtractor):
    name = "bank_statement_test_stub"
    doc_types = ("bank_statement",)
    needs = ("text",)
    cost = FREE
    confidence = 0.9

    def __init__(self, values):
        self._values = values

    def extract(self, source, doc_type, wanted, env=None):
        return dict(self._values) if self._values else None


@contextlib.contextmanager
def _only(extractor):
    saved = dict(registry._EXTRACTORS)
    registry._EXTRACTORS.clear()
    try:
        registry.register_extractor(extractor)
        yield
    finally:
        registry._EXTRACTORS.clear()
        registry._EXTRACTORS.update(saved)


@tagged("post_install", "-at_install")
class TestBankStatementExtraction(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.company_data["default_journal_bank"]

    def _statement(self, **values):
        vals = {"journal_id": self.journal.id, "name": "Statement under test"}
        vals.update(values)
        statement = self.env["account.bank.statement"].create(vals)
        self.env["ir.attachment"].create(
            {
                "name": "statement.txt",
                "res_model": "account.bank.statement",
                "res_id": statement.id,
                "mimetype": "text/plain",
                "raw": b"a bank statement with words on it",
            }
        )
        return statement

    def _read(self, statement, values):
        with _only(_Stub(values)):
            return statement._extract_document()

    def test_a_statement_is_read_into_the_fields_a_person_edits(self):
        statement = self._statement()
        self._read(
            statement,
            {
                "opening_balance": 100.0,
                "closing_balance": 250.0,
                "period_end": "2026-03-31",
                "transactions": [
                    {"amount": 100.0, "date": "2026-03-02", "description": "Deposit"},
                    {"amount": 50.0, "date": "2026-03-09", "description": "Refund"},
                ],
            },
        )
        self.assertEqual(statement.balance_start, 100.0)
        self.assertEqual(statement.balance_end_real, 250.0)
        self.assertEqual(len(statement.line_ids), 2)
        self.assertEqual(
            statement.line_ids.sorted(lambda line: (line.date, line.id)).mapped(
                "payment_ref"
            ),
            ["Deposit", "Refund"],
        )

    def test_a_statement_that_adds_up_is_complete(self):
        statement = self._statement()
        self._read(
            statement,
            {
                "opening_balance": 100.0,
                "closing_balance": 250.0,
                "transactions": [
                    {"amount": 100.0, "date": "2026-03-02", "description": "Deposit"},
                    {"amount": 50.0, "date": "2026-03-09", "description": "Refund"},
                ],
            },
        )
        self.assertEqual(statement.balance_end, 250.0)
        self.assertTrue(statement.is_complete)

    def test_a_statement_that_does_not_add_up_says_so(self):
        statement = self._statement()
        self._read(
            statement,
            {
                "opening_balance": 100.0,
                "closing_balance": 999.0,
                "transactions": [
                    {"amount": 100.0, "date": "2026-03-02", "description": "Deposit"},
                ],
            },
        )
        self.assertEqual(statement.balance_end, 200.0)
        self.assertEqual(statement.balance_end_real, 999.0)
        self.assertFalse(statement.is_complete)

    def test_a_balance_a_person_typed_is_left_alone(self):
        statement = self._statement(balance_start=42.0)
        self._read(statement, {"opening_balance": 100.0, "transactions": [{}]})
        self.assertEqual(statement.balance_start, 42.0)

    def test_a_statement_with_transactions_is_not_read_into(self):
        statement = self._statement()
        statement.line_ids = [
            (
                0,
                0,
                {"amount": 5.0, "payment_ref": "typed by hand", "date": "2026-03-01"},
            )
        ]
        self._read(
            statement,
            {
                "transactions": [
                    {"amount": 100.0, "date": "2026-03-02", "description": "Deposit"}
                ]
            },
        )
        self.assertEqual(statement.line_ids.mapped("payment_ref"), ["typed by hand"])

    def test_an_unreadable_row_drops_itself_and_keeps_the_rest(self):
        statement = self._statement()
        self._read(
            statement,
            {
                "transactions": [
                    {"amount": "not a number", "description": "Broken"},
                    {"amount": "1.234,56", "description": "European"},
                    {"description": "No amount at all"},
                    "not even a dict",
                ]
            },
        )
        self.assertEqual(statement.line_ids.mapped("payment_ref"), ["European"])
        self.assertEqual(statement.line_ids.amount, 1234.56)

    def test_a_transaction_with_no_description_is_dropped_rather_than_invented(self):
        statement = self._statement()
        self._read(
            statement,
            {
                "opening_balance": 0.0,
                "closing_balance": 10.0,
                "transactions": [{"amount": 10.0}],
            },
        )
        self.assertFalse(statement.line_ids)
        self.assertEqual(statement.balance_end_real, 10.0)
        self.assertFalse(statement.is_complete)

    def test_reading_a_statement_that_already_has_lines_is_refused(self):
        statement = self._statement()
        statement.line_ids = [
            (0, 0, {"amount": 5.0, "payment_ref": "typed", "date": "2026-03-01"})
        ]
        with self.assertRaises(UserError):
            statement.action_extract_document()

    def test_the_journal_routes_a_scan_and_leaves_other_formats_alone(self):
        journal = self.journal
        scan = self.env["ir.attachment"].create(
            {"name": "statement.png", "raw": b"\x89PNG\r\n\x1a\n" + b"\x00" * 32}
        )
        ledger = self.env["ir.attachment"].create(
            {"name": "statement.csv", "raw": b"date,amount\n2026-03-01,10\n"}
        )
        self.assertTrue(journal._is_attachment_extractable(scan))
        self.assertFalse(journal._is_attachment_extractable(ledger))

    def test_the_journal_routes_by_the_declared_type_as_the_reading_does(self):
        journal = self.journal
        declared_scan = self.env["ir.attachment"].create(
            {
                "name": "statement.png",
                "mimetype": "image/png",
                "raw": b"bytes no sniffer places",
            }
        )
        declared_ledger = self.env["ir.attachment"].create(
            {
                "name": "statement.csv",
                "mimetype": "text/csv",
                "raw": b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
            }
        )
        self.assertTrue(journal._is_attachment_extractable(declared_scan))
        self.assertFalse(journal._is_attachment_extractable(declared_ledger))

    def test_a_mixed_upload_is_refused_rather_than_half_read(self):
        journal = self.journal
        scan = self.env["ir.attachment"].create(
            {"name": "statement.png", "raw": b"\x89PNG\r\n\x1a\n" + b"\x00" * 32}
        )
        ledger = self.env["ir.attachment"].create(
            {"name": "statement.csv", "raw": b"date,amount\n2026-03-01,10\n"}
        )
        with self.assertRaises(UserError):
            journal._import_bank_statement(scan | ledger)
