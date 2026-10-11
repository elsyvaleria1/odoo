{
    "name": "UNSPSC Product and Unit Codes",
    "version": "0.3",
    "oldest_upgradable_version": "0.3",
    "category": "Accounting/Accounting",
    "summary": "Assign UNSPSC classification codes to products and units",
    "description": "Loads the supplied UNSPSC code data, exposes classification fields on products and units and validates the applicability of selected codes.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "views/product_views.xml",
        "security/ir.access.csv",
    ],
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
