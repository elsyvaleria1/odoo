{
    "name": "Purchase Agreements",
    "version": "0.8",
    "oldest_upgradable_version": "0.8",
    "category": "Supply Chain/Purchase",
    "summary": "Define vendor agreements with prices and quantity or value commitments",
    "description": """
This module allows you to manage your Purchase Agreements.
===========================================================

Blanket orders: agreements with vendors that commit prices, and a quantity or a
value, over a period; the purchase orders placed against them draw from the
commitment. Calls for tenders live in purchase_tender.
""",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "purchase",
        "trade_agreement",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "security/res_groups.xml",
        "security/ir.access.csv",
        "data/purchase_agreement_data.xml",
        "views/product_views.xml",
        "views/purchase_views.xml",
        "views/purchase_agreement_views.xml",
        "reports/purchase_agreement_report.xml",
        "reports/report_purchaseagreement.xml",
        "views/purchase_agreement_menus.xml",
    ],
    "demo": [
        "demo/purchase_agreement_demo.xml",
    ],
}
