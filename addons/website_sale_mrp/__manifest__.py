{
    "name": "Website Kit Cart Availability",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Account for shared kit components when calculating unavailable cart quantities",
    "description": "Adds a storefront quantity endpoint and sale-order calculations for kits and their components already present in the cart. Uses phantom bills of materials and free component stock to adjust availability; stock management and checkout are supplied by dependencies.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website_sale_stock",
        "sale_mrp",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_mrp/static/src/js/**/*",
        ],
        "web.assets_tests": [
            "website_sale_mrp/static/tests/tours/*",
        ],
    },
    "auto_install": True,
}
