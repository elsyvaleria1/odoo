{
    "name": "Custom Tax Formulas",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Calculate tax amounts using restricted expressions and product values",
    "description": "Adds a custom formula tax type evaluated in server and browser tax computations. Expressions use the tax base, unit price, quantity and permitted nonrelational product or unit fields, subject to an operator and function allowlist. Configured formulas replace the amount calculation; there is no separate applicability script.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "views/account_tax_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "tax_python/static/src/helpers/*.js",
        ],
        "account.assets_tests_shared_js_python": [
            "tax_python/static/src/helpers/*.js",
        ],
    },
}
