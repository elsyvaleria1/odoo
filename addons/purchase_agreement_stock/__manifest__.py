{
    "name": "Purchase Agreement Procurement",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Supply Chain/Purchase",
    "sequence": 70,
    "summary": "Use purchase agreements when preparing replenishment orders",
    "description": "Extend purchase and procurement values with the selected agreement and picking type. Supplies agreement-related stock configuration and views.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "purchase_agreement",
        "purchase_stock",
    ],
    "data": [
        "security/ir.access.csv",
        "data/purchase_agreement_stock_data.xml",
        "views/purchase_agreement_views.xml",
    ],
    "auto_install": True,
}
