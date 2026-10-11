{
    "name": "Website Mondial Relay Pickup Selection",
    "version": "0.1",
    "category": "Website/Website",
    "summary": "Select a Mondial Relay pickup point as the checkout delivery address",
    "description": "Adds pickup-point selection and shipping-address updates for carts using a Mondial Relay carrier. Requires an identified cart customer and a pickup country allowed by the carrier. Checkout checks that the selected carrier and pickup address agree; provider access comes from the delivery integration.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale",
        "delivery_mondialrelay",
    ],
    "data": [
        "views/delivery_carrier_views.xml",
        "views/delivery_form_templates.xml",
        "views/templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_mondialrelay/static/src/**/*",
        ],
    },
    "auto_install": True,
}
