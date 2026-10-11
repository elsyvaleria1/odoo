{
    "name": "Deprecated Peppol Reference Fields",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Retain deprecated invoice reference fields for Peppol",
    "description": "Adds contract, project, originator, despatch, additional-document, accounting-cost and delivery-location references to invoice forms. This deprecated addon only stores these fields; it does not implement their Peppol export.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
        "account_edi_ubl_cii",
    ],
    "data": [
        "views/account_move_views.xml",
    ],
}
