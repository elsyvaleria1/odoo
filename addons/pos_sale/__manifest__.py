{
    "name": "POS Sales Order Settlement",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Settle sales orders and collect down payments through the point of sale",
    "description": "Adds sales-order lookup, settlement and fixed or percentage down payments in POS, with links to originating sales lines and invoice quantities. Also extends sales-team and sales-analysis integration. Down payments require a configured POS down-payment product; invoicing and fulfillment follow the associated order and POS configuration.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "point_of_sale",
        "sale",
        "sale_team",
    ],
    "data": [
        "data/pos_sale_data.xml",
        "security/ir.access.csv",
        "views/point_of_sale_report.xml",
        "views/sale_order_views.xml",
        "views/pos_order_views.xml",
        "views/sales_team_views.xml",
        "views/res_config_settings_views.xml",
        "views/stock_template.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_sale/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_sale/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_sale/static/tests/unit/**/*",
        ],
    },
    "auto_install": True,
    "post_init_hook": "_pos_sale_post_init",
}
