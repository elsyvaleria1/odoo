{
    "name": "Automated WhatsApp Campaigns",
    "version": "1.0",
    "category": "Marketing/Marketing Automation",
    "summary": "Send WhatsApp template steps in marketing workflows",
    "description": "Adds WhatsApp activity execution, message statistics and tracked links to campaigns. Requires a configured WhatsApp account and usable message templates.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "marketing_automation",
        "whatsapp",
    ],
    "data": [
        "views/marketing_activity_data_templates.xml",
        "views/marketing_activity_views.xml",
        "views/whatsapp_template_views.xml",
        "views/marketing_campaign_views.xml",
        "views/marketing_participant_views.xml",
        "security/marketing_automation_whatsapp_security.xml",
    ],
    "auto_install": True,
}
