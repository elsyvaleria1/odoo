{
    "name": "External Sales Tax Calculation",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Calculate sales order taxes through configured external tax services",
    "description": "Prepare sales lines for external tax calculation during quotation and order processing. Provider-specific modules implement the tax service and its credentials.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account_external_tax",
        "sale",
    ],
    "data": [
        "views/sale_order_views.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "sale_external_tax/static/tests/tours/sale_external_optional_products.js",
        ],
    },
    "auto_install": True,
}
