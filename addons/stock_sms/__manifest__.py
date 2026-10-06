{
    "name": "Delivery SMS Notifications",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Supply Chain/Inventory",
    "summary": "Send text-message confirmations for stock deliveries",
    "description": "Adds configurable SMS templates and delivery-confirmation handling to stock transfers. Sending uses the configured SMS service.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "sms",
    ],
    "data": [
        "data/sms_data.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_stock_picking_validate_first_sms_views.xml",
        "security/ir.access.csv",
    ],
    "auto_install": True,
    "post_init_hook": "_update_default_sms_template",
    "uninstall_hook": "_reset_sms_text_confirmation",
}
