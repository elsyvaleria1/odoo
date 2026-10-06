{
    "name": "Storefront Product Comparison",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Compare selected storefront products by their configured attributes",
    "description": "Adds a product comparison page, comparison controls and attribute categories that organize the table. Also supplies a product-page attribute summary template; useful comparisons require populated product attributes and do not guarantee faster purchasing decisions.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website_sale",
    ],
    "data": [
        "security/ir.access.csv",
        "views/website_sale_comparison_template.xml",
        "views/website_sale_comparison_view.xml",
        "views/website_sale_comparison_menus.xml",
    ],
    "demo": [
        "demo/website_sale_comparison_data.xml",
        "demo/website_sale_comparison_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_comparison/static/src/interactions/**/*",
            "website_sale_comparison/static/src/scss/website_sale_comparison.options.scss",
            "website_sale_comparison/static/src/scss/website_sale_comparison.scss",
            "website_sale_comparison/static/src/js/**/*",
        ],
        "web.assets_tests": [
            "website_sale_comparison/static/tests/**/*",
        ],
        "website.website_builder_assets": [
            "website_sale_comparison/static/src/website_builder/**/*",
        ],
    },
    "auto_install": True,
}
