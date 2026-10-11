{
    "name": "Tax Computation Engine",
    "version": "19.0.1.5.0",
    "oldest_upgradable_version": "19.0.1.5.0",
    "category": "Hidden",
    "summary": "Calculate configured product taxes and fiscal-position mappings",
    "description": "Defines tax records, groups, repartition data and fiscal-position tax mappings used by order calculations. Adds product tax defaults and company tax settings. Accounting-specific journal accounts and posting behavior are supplied by the accounting addon.",
    "author": "Odoo Community",
    "website": "https://www.odoo.com",
    "license": "Other OSI approved licence",
    "depends": [
        "product",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "tax/static/src/helpers/*.js",
        ],
    },
}
