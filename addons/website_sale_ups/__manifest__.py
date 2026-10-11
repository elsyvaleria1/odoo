{
    "name": "Website UPS Customer Account Billing",
    "category": "Shipping Connectors",
    "summary": "Accept a customer UPS account on eligible website delivery orders",
    "description": "Adds checkout routes for setting or clearing the UPS account and checking carrier service availability. The selected carrier must enable bill-my-account; shipment rating and account acceptance depend on the UPS integration.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "delivery_ups",
        "website_sale",
    ],
    "data": [
        "views/delivery_ups_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_ups/static/src/**/*",
        ],
    },
    "auto_install": True,
}
