{
    "name": "Customer Order Status Display",
    "version": "1.0.0",
    "category": "Sales/Point of Sale",
    "sequence": 7,
    "summary": "Show customers the preparation status of their orders",
    "description": "Provides a public-facing order-status display and updates it from preparation-stage changes.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_enterprise",
        "pos_self_order",
    ],
    "data": [
        "views/index.xml",
        "views/preparation_display_view.xml",
    ],
    "assets": {
        "pos_order_tracking_display.assets": [
            (
                "include",
                "point_of_sale.base_app",
            ),
            "point_of_sale/static/src/utils.js",
            "point_of_sale/static/src/app/components/odoo_logo/*",
            "pos_order_tracking_display/static/src/**/*",
            "pos_enterprise/static/src/app/utils/utils.js",
        ],
    },
    "esm": {
        "bundles": [
            "pos_order_tracking_display.assets",
        ],
    },
    "auto_install": True,
}
