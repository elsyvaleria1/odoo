{
    "name": "WhatsApp Payment Follow-Ups",
    "version": "1.0",
    "category": "Productivity/WhatsApp",
    "summary": "Send payment follow-ups using WhatsApp templates",
    "description": "Adds WhatsApp delivery to follow-up levels and the follow-up wizard. Requires a configured WhatsApp account, a usable template and a recipient number.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account_followup",
        "whatsapp",
    ],
    "data": [
        "data/whatsapp_template_data.xml",
        "views/account_followup_line_views.xml",
        "wizards/wizard_res_partner_send_followup_views.xml",
    ],
    "auto_install": True,
}
