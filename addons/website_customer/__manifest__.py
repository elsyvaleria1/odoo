{
    "name": "Published Customer References",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Display published customer references with detail pages and industry filters",
    "description": "Adds a customer reference listing, detail templates and contact publication controls, with map integration supplied by the dependencies. Display depends on configured customer records and publication; this addon does not promise lead generation or commercial results.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website_crm_partner_assign",
        "website_partner",
        "website_google_map",
    ],
    "data": [
        "views/website_customer_templates.xml",
        "views/res_partner_views.xml",
        "security/ir.access.csv",
        "views/website_customer_menus.xml",
    ],
    "demo": [
        "demo/res_partner_demo.xml",
    ],
    "assets": {
        "website.website_builder_assets": [
            "website_customer/static/src/website_builder/**/*",
        ],
        "web.assets_tests": [
            "website_customer/static/tests/tours/*.js",
        ],
    },
}
