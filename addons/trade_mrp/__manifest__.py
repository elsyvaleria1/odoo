{
    "name": "Order Kit Fulfillment Quantities",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Calculate transferred kit quantities from component stock moves",
    "description": "Extends stock-enabled order lines with phantom bill-of-materials lookup and component-based delivered or received quantities. Uses the applicable order direction, completed moves and unit conversion, with separate dropship and missing-bill-of-materials handling. Requires configured kit products and adopting stock order models.",
    "author": "Odoo Community",
    "website": "https://www.odoo.com",
    "license": "LGPL-3",
    "depends": [
        "trade_stock",
        "mrp",
    ],
    "auto_install": True,
}
