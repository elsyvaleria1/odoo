{
    "name": "Self-Order Sales Team",
    "category": "Sales/Point of Sale",
    "summary": "Assign sales-team configuration to self-ordering POS kiosks",
    "description": "Provide the kiosk sales team and extend the POS kiosk settings onchange. Connects self-order configuration with the sales-team setup.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_sale",
        "pos_self_order",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "data/kiosk_sale_team.xml",
    ],
    "auto_install": True,
}
