{
    "name": "Debit Notes",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Accounting",
    "summary": "Create debit notes linked to invoices and bills",
    "description": "Provides a debit-note wizard with date, reason, journal and optional line copying. Links the new entries to their source documents and supports a separate debit-note sequence.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "wizards/wizard_account_move_create_debit_note_views.xml",
        "views/account_move_view.xml",
        "views/account_journal_views.xml",
        "security/ir.access.csv",
    ],
}
