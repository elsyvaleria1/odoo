{
    "name": "Order Variant Grid Infrastructure",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Provide reusable variant grids for order-line quantities and reports",
    "description": "Adds a mixin that loads product variant grids, applies edited quantities and prepares report grids for adopting order models. Nonzero quantity changes are refused when a variant matches multiple eligible order lines; sales and purchase extensions supply their interface and direction-specific rules.",
    "author": "Odoo Community",
    "website": "https://www.odoo.com",
    "license": "Other OSI approved licence",
    "depends": [
        "trade",
        "product_matrix",
    ],
}
