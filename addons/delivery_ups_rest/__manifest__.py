{
    "name": "UPS REST Shipping",
    "version": "0.2",
    "oldest_upgradable_version": "0.2",
    "category": "Shipping Connectors",
    "summary": "Request UPS rates and shipment labels through the REST integration",
    "description": "Implements rate requests, shipment creation, return labels, tracking links and cancellation using UPS REST endpoints. Requires a UPS shipper account, client credentials and configured package and service options.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_delivery",
        "mail",
    ],
    "data": [
        "data/ups_package_data.xml",
        "views/delivery_ups.xml",
        "views/sale_order_views.xml",
        "views/res_partner.xml",
    ],
    "application": True,
}
