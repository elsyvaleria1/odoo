{
    "name": "Vendor Bill Document Extraction",
    "version": "19.0.1.0.1",
    "oldest_upgradable_version": "19.0.1.0.1",
    "category": "Accounting",
    "summary": "Populate eligible bill headers and offer extracted lines for review",
    "description": "Adds the extraction mixin to accounting moves with vendor-bill eligibility checks and supplier matching. Exposes extracted line proposals in a review wizard before adding accepted lines to the bill. Requires a usable extraction strategy and source attachment; accounting users remain responsible for products, accounts, taxes and posting.",
    "author": "AgroMarin",
    "website": "https://agromarin.com",
    "license": "LGPL-3",
    "depends": [
        "account",
        "extract",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/wizard_account_move_add_extracted_line_views.xml",
        "views/account_move_views.xml",
    ],
}
