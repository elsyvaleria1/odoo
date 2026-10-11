{
    "name": "Restaurant UrbanPiper Orders",
    "category": "Sales/Point of Sale",
    "summary": "Adapt the restaurant POS interface for UrbanPiper delivery orders",
    "description": "Load restaurant-specific frontend extensions for UrbanPiper orders. Uses the UrbanPiper connector for delivery-platform communication.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_restaurant",
        "pos_urban_piper",
    ],
    "assets": {
        "web.assets_backend": [],
        "point_of_sale._assets_pos": [
            "pos_restaurant_urban_piper/static/src/**/*",
        ],
    },
    "auto_install": True,
}
