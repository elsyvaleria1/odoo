{
    "name": "Sales Order Margins",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Calculate sales order margins from line revenues and costs",
    "description": "Add cost and margin calculations to sales lines and order totals. Extend sales analysis with margin information.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "sale",
    ],
    "data": [
        "views/sale_order_views.xml",
    ],
    "demo": [
        "demo/sale_margin_demo.xml",
    ],
}
