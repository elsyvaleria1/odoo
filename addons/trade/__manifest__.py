{
    "name": "Trade Order Framework",
    "version": "19.0.3.8.0",
    "oldest_upgradable_version": "19.0.3.6.7",
    "category": "Hidden",
    "summary": "Share order workflows, amounts and pricing helpers across trade applications",
    "description": "Provides abstract order and line mixins for workflow, totals, pricing, merging, templates and reporting. Adds shared order configuration and contact order statistics. Sales and purchasing addons define the concrete business orders and their application interfaces.",
    "author": "Odoo Community",
    "website": "https://www.odoo.com",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "portal",
        "loss_reason",
        "product",
        "analytic",
        "tax",
        "payment_term",
        "mixin_report_sql",
    ],
    "data": [
        "security/ir.access.csv",
        "views/res_partner_tag_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "trade/static/src/components/**/*",
        ],
        "web.assets_unit_tests": [
            "trade/static/tests/**/*.test.js",
        ],
    },
}
