{
    "name": "WhatsApp Outgoing Transfer Confirmation",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Productivity/WhatsApp",
    "summary": "Queue WhatsApp confirmations for outgoing transfers when company messaging is enabled",
    "description": "Extends transfer confirmation handling to queue messages through the configured stock WhatsApp template. Requires outgoing operation type, enabled company WhatsApp confirmation and a selected template; incoming and internal transfers do not use this path.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_enterprise",
        "whatsapp",
    ],
    "data": [
        "data/whatsapp_template_data.xml",
        "views/res_config_settings_views.xml",
    ],
    "auto_install": True,
    "uninstall_hook": "_reset_whatsapp_text_confirmation",
}
