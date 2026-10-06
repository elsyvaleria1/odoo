{
    "name": "QIF Bank Statement Import",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Import bank transactions from QIF statement files",
    "description": "Add QIF parsing to the bank statement import flow and convert transactions into bank statement lines. Review duplicate transactions when importing overlapping files; these formats do not supply reliable unique transaction identifiers.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account_bank_statement_import",
    ],
    "data": [
        "views/account_journal_views.xml",
    ],
}
