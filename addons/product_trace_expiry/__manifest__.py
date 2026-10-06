{
    "name": "Lot and Serial Number Expiration Dates",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Compute expiration, best-before, removal and alert dates on lots",
    "description": "Adds each product's shelf-life settings (expiration, best-before, removal and alert delays, and the category default) and computes the corresponding dates on its lots and serial numbers. Removal strategies, stock alerts and fresh quantities stay in product_expiry, which depends on this addon.",
    "author": "Odoo S.A., AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "product_trace",
    ],
    "data": [
        "views/product_trace_views.xml",
    ],
}
