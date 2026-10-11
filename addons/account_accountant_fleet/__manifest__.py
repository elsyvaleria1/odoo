{
    "name": "Asset Tax Line Grouping",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Keep tax calculations and journal lines grouped by asset",
    "description": "Carry the asset through tax computation and tax-line grouping. Match a tax line to base lines with the same asset, keeping different assets separate.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account_fleet",
        "account",
    ],
    "data": [
        "views/account_move_views.xml",
    ],
    "auto_install": True,
}
