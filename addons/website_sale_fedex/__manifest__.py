{
    "name": "FedEx Website Pickup Locations",
    "category": "Shipping Connectors",
    "summary": "Retrieve FedEx pickup locations for website delivery selection",
    "description": "Adds carrier radius configuration and FedEx location requests with address and opening-hour formatting. Requires configured FedEx service access and a supported pickup flow; the addon does not maintain its own pickup-point directory.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "delivery_fedex",
        "website_sale",
    ],
    "data": [
        "views/delivery_fedex_view.xml",
    ],
    "auto_install": True,
}
