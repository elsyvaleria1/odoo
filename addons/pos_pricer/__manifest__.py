{
    "name": "Pricer Electronic Shelf Labels",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Update product information on configured Pricer shelf labels",
    "description": "Links products to Pricer stores and tags and sends product and price updates through configured service credentials. Requires supported labels and Pricer service access.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "credential",
        "integration",
        "product",
        "point_of_sale",
    ],
    "data": [
        "security/ir.access.csv",
        "views/pricer_tag_views.xml",
        "views/pricer_store_views.xml",
        "views/product_views.xml",
        "data/pricer_ir_cron.xml",
        "data/pos_pricer_data.xml",
        "data/pos_config_data.xml",
        "views/pos_pricer_menus.xml",
    ],
    "demo": [
        "demo/pricelist_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pos_pricer/static/**/*",
        ],
    },
}
