{
    "name": "Product Invoice Margins",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Sales",
    "summary": "Analyse product sales, purchase amounts and margins from invoices",
    "description": "Provide a product margin reporting wizard and calculated invoice-based indicators. Users select the reporting conditions before viewing product amounts.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/wizard_product_product_view_margin_views.xml",
        "views/product_product_views.xml",
        "views/product_margin_menus.xml",
    ],
}
