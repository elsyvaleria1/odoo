{
    "name": "Sales Service Purchasing",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Generate purchase orders for configured outsourced sales services",
    "description": "Adds the service-to-purchase product option and hooks for creating and updating linked purchase lines from confirmed sales lines. Exposes cross-document actions and cancellation notifications. Requires suitable vendor and service configuration; ordinary products and services without the option do not use this flow.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/",
    "license": "LGPL-3",
    "depends": [
        "sale",
        "purchase",
    ],
    "data": [
        "data/mail_templates.xml",
        "views/product_views.xml",
        "views/sale_order_views.xml",
        "views/purchase_order_views.xml",
    ],
    "auto_install": True,
}
