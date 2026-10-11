{
    "name": "Accounting Document Templates",
    "version": "19.0.1.4.0",
    "oldest_upgradable_version": "19.0.1.3.0",
    "category": "Accounting/Accounting",
    "summary": "Create accounting documents and payments from reusable templates",
    "description": "Stores journal codes, account prefixes, partners and product lines for a document-generation wizard. Supports journal entries, invoices, credit notes and payment templates, with configurable amount distribution and product-category selection. Journal and account codes must resolve in the selected company; running a template creates a document rather than scheduling recurring execution.",
    "author": "AgroMarin, Akretion, Odoo Community Association (OCA)",
    "website": "https://agromarin.com",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
        "analytic",
        "mail",
        "product",
    ],
    "data": [
        "security/ir.access.csv",
        "views/account_move_template_views.xml",
        "wizards/account_move_template_run_views.xml",
        "views/account_move_template_menus.xml",
    ],
}
