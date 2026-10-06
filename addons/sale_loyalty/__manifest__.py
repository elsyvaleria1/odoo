{
    "name": "Sales Loyalty Programs",
    "version": "1.3",
    "oldest_upgradable_version": "1.2",
    "category": "Sales/Sales",
    "summary": "Apply configured coupons, rewards and loyalty points to sales orders",
    "description": "Connects loyalty programs to sales orders with coupon and reward wizards, reward lines, point tracking and related invoice handling. Requires eligible programs, rules and products configured in the loyalty dependency. This bridge supplies the sales-order workflow; website and point-of-sale interfaces use their own addons.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "sale",
        "loyalty",
    ],
    "data": [
        "security/sale_loyalty_security.xml",
        "security/ir.access.csv",
        "data/sale_loyalty_data.xml",
        "wizards/wizard_sale_order_add_coupon_views.xml",
        "wizards/wizard_sale_order_add_reward_views.xml",
        "views/loyalty_card_views.xml",
        "views/loyalty_program_views.xml",
        "views/sale_order_views.xml",
        "views/sale_portal_templates.xml",
        "views/res_partner_views.xml",
        "views/sale_loyalty_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_loyalty/static/src/**/*",
        ],
    },
    "auto_install": True,
    "uninstall_hook": "uninstall_hook",
}
