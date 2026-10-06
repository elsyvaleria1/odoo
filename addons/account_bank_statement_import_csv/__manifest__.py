{
    "name": "CSV Bank Statement Import",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Import bank transactions from CSV statement files",
    "description": "Add CSV parsing to the bank statement import flow and convert transactions into bank statement lines. Review duplicate transactions when importing overlapping files; these formats do not supply reliable unique transaction identifiers.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account_bank_statement_import",
        "base_import",
    ],
    "data": [
        "views/bank_rec_widget_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_bank_statement_import_csv/static/src/**/*",
        ],
    },
    "auto_install": True,
}
