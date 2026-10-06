{
    "name": "Electronic Invoice Processing",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Track electronic invoice documents and their processing states",
    "description": "Provide invoice EDI format and document models, error tracking and scheduled processing. Format-specific modules implement the document payloads and service connections.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.access.csv",
        "views/account_edi_document_views.xml",
        "views/account_move_views.xml",
        "views/account_journal_views.xml",
        "data/cron.xml",
    ],
}
