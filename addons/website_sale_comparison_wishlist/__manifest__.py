{
    "name": "Wishlist Product Comparison",
    "category": "Website/Website",
    "summary": "Compare products from the website wishlist",
    "description": "Add comparison controls to wishlist products. Selected products join the website product-comparison list, using its existing duplicate and maximum-product checks.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website_sale_comparison",
        "website_sale_wishlist",
    ],
    "data": [
        "views/templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_comparison_wishlist/static/src/**/*",
        ],
    },
    "auto_install": True,
}
