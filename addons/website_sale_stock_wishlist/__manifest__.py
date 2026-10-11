{
    "name": "Wishlist Stock Notifications",
    "category": "Website/Website",
    "summary": "Let wishlist users request email notifications when products return to stock",
    "description": "Expose stock-notification subscription controls on wishlist products. Connects wishlist entries to the product availability notification feature supplied by website stock sales.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale_stock",
        "website_sale_wishlist",
    ],
    "data": [
        "views/website_sale_stock_wishlist_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_stock_wishlist/static/src/interactions/**/*",
            "website_sale_stock_wishlist/static/src/scss/**/*",
            "website_sale_stock_wishlist/static/src/xml/**/*",
            (
                "before",
                "website_sale/static/src/interactions/website_sale.js",
                "website_sale_stock_wishlist/static/src/js/variant_mixin.js",
            ),
        ],
    },
    "auto_install": True,
}
