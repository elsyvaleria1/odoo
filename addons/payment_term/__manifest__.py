{
    "name": "Payment Terms",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Define installment schedules, due dates and early-payment discounts",
    "description": "Stores payment terms and their lines, computes schedule examples and adds customer and supplier term defaults to contacts. Supplies reusable term calculations and configuration views. Trade and accounting addons consume the terms on orders, invoices and payments; this module does not create those documents itself.",
    "author": "Odoo S.A., AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "web",
    ],
    "data": [
        "security/ir.access.csv",
        "views/account_payment_term_views.xml",
        "data/account_payment_term_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "payment_term/static/src/scss/account_payment_term.scss",
            "payment_term/static/src/components/**/*",
        ],
    },
}
