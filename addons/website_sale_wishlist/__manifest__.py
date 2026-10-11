{
    "name": "Storefront Product Wishlist",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Save storefront products in a visitor session or customer wishlist",
    "description": "Adds wishlist records, storefront controls and add, remove and listing routes. Anonymous entries are associated with the browser session and can be merged into the customer wishlist at login; saved items do not reserve stock or guarantee future availability.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale",
    ],
    "data": [
        "security/ir.access.csv",
        "views/website_sale_wishlist_template.xml",
        "views/website_sale_wishlist_template_svg.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_wishlist/static/src/interactions/**/*",
            "website_sale_wishlist/static/src/scss/**/*",
            "website_sale_wishlist/static/src/js/**/*",
        ],
        "web.assets_tests": [
            "website_sale_wishlist/static/tests/**/*",
        ],
        "website.website_builder_assets": [
            "website_sale_wishlist/static/src/website_builder/**/*",
        ],
    },
    "auto_install": True,
}
