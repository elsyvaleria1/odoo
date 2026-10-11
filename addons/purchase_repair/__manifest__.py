{
    "name": "Repair Purchase Navigation",
    "version": "1.0",
    "category": "Supply Chain/Purchase",
    "summary": "Open related purchases from repairs and repairs from purchases",
    "description": "Adds linked-record counts and navigation actions to purchase and repair orders.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "repair",
        "purchase_stock",
    ],
    "data": [
        "views/purchase_views.xml",
        "views/repair_views.xml",
    ],
    "auto_install": True,
}
