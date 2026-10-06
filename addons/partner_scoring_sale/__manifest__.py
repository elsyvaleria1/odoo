{
    "name": "Customer Tiers on Sales Orders",
    "version": "19.0.1.0.0",
    "category": "Sales/Sales",
    "summary": "Record customer tiers at order confirmation and expose them in sales analysis",
    "description": "Adds a stored order tier and a confirmation snapshot used by sales reporting. A nonempty snapshot takes precedence over the current customer tier; if no tier was captured, the displayed tier continues to follow the commercial partner.",
    "author": "AgroMarin",
    "website": "https://agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "partner_scoring",
        "sale",
    ],
    "data": [
        "views/sale_order_views.xml",
        "reports/sale_report_views.xml",
    ],
    "auto_install": True,
}
