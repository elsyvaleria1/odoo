{
    "name": "Sendcloud Website Pickup Locations",
    "category": "Shipping Connectors",
    "summary": "Retrieve nearby Sendcloud pickup locations for configured delivery methods",
    "description": "Adds Sendcloud location lookup and search-radius settings to website delivery selection. Requires a Sendcloud carrier with pickup locations enabled, service credentials and a supported shipping method; location availability comes from the provider.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "delivery_sendcloud",
        "website_sale",
    ],
    "data": [
        "views/delivery_sendcloud_view.xml",
    ],
    "auto_install": True,
}
