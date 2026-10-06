{
    "name": "Gelato Stock Procurement Exclusion",
    "category": "Sales/Sales",
    "summary": "Skip local stock procurement for Gelato order lines",
    "description": "Filters Gelato products out of the sales stock-rule launch so the external fulfillment flow does not create local procurement for those lines.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "sale_gelato",
        "sale_stock",
    ],
    "auto_install": True,
}
