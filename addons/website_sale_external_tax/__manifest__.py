{
    "name": "Website External Tax Checkout",
    "category": "Accounting/Accounting",
    "summary": "Calculate externally supplied taxes during website checkout",
    "description": "Extend checkout tax validation, payment context and order totals for external tax calculation. Uses the order's configured tax-provider integration.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_external_tax",
        "website_sale",
    ],
    "data": [
        "views/templates.xml",
    ],
    "auto_install": True,
}
