{
    "name": "eCommerce Loyalty and Promotions",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Website/Website",
    "summary": "Apply eligible coupons, rewards and gift cards in the online store",
    "description": "Connects sales loyalty programs to eCommerce carts, coupon activation and reward selection. Adds website eligibility settings, sharing links and wallet top-up handling. Discounts and rewards follow the configured programs and their conditions.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale",
        "website_links",
        "sale_loyalty",
    ],
    "data": [
        "security/ir.access.csv",
        "views/loyalty_card_views.xml",
        "views/loyalty_program_views.xml",
        "views/website_sale_templates.xml",
        "views/website_sale_loyalty_menus.xml",
        "wizards/wizard_loyalty_program_share_views.xml",
        "wizards/res_config_settings_views.xml",
    ],
    "demo": [
        "demo/product_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_loyalty/static/src/js/**/*",
            "website_sale_loyalty/static/src/interactions/**/*",
        ],
        "web.assets_tests": [
            "website_sale_loyalty/static/tests/**/*",
        ],
        "website.website_builder_assets": [
            "website_sale_loyalty/static/src/website_builder/**/*",
        ],
    },
    "auto_install": [
        "website_sale",
        "sale_loyalty",
    ],
}
