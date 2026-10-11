{
    "name": "Sales Agreements",
    "version": "19.0.1.0.0",
    "category": "Sales/Sales",
    "summary": "Apply customer blanket-agreement terms to sales orders",
    "description": "Adds customer agreement records and lines linked to sales orders, with agreed quantities, dates, prices and price breaks. Order lines use the agreement pricing helpers and confirmed quantities contribute to agreement usage. Requires configured customer agreements and uses the shared trade-agreement lifecycle.",
    "author": "Odoo Community",
    "website": "https://www.odoo.com",
    "license": "Other OSI approved licence",
    "depends": [
        "sale",
        "trade_agreement",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "security/ir.access.csv",
        "data/sale_agreement_data.xml",
        "views/sale_agreement_views.xml",
        "views/sale_order_views.xml",
        "views/sale_agreement_menus.xml",
    ],
}
