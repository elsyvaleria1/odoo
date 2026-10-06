{
    "name": "Product Lots and Serial Numbers",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Identify products by lot or by serial number",
    "description": "Provides the lot/serial number record (product.trace) and each product's tracking mode, naming sequence and name format. A lot identifies a batch of units and a serial number exactly one unit; both are one record kind, chosen by the product's tracking. Stock, expiry and asset addons extend it; this addon keeps no quantities, locations or moves.",
    "author": "Odoo S.A., AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "product",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "views/product_trace_views.xml",
    ],
}
