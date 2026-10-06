{
    "name": "Helpdesk Stage SMS Notifications",
    "version": "1.0",
    "category": "Services/Helpdesk",
    "summary": "Send text messages when tickets enter configured stages",
    "description": "Adds an SMS template to helpdesk stages and sends it on applicable ticket creation or stage changes through the configured SMS service.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "helpdesk",
        "sms",
    ],
    "data": [
        "views/helpdesk_stage_views.xml",
        "views/helpdesk_sms_views.xml",
        "security/ir.access.csv",
    ],
    "auto_install": True,
}
