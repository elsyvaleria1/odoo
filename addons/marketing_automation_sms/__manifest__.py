{
    "name": "Automated SMS Campaigns",
    "version": "1.0",
    "category": "Marketing/Marketing Automation",
    "summary": "Send SMS steps in marketing automation workflows",
    "description": "Adds SMS activity execution and delivery-event tracking to campaign workflows. Requires the SMS marketing integration and configured sending service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "marketing_automation",
        "mass_mailing_sms",
    ],
    "data": [
        "views/mailing_mailing_views.xml",
        "views/mailing_trace_views.xml",
        "views/marketing_activity_views.xml",
        "views/marketing_campaign_views.xml",
        "views/marketing_participant_views.xml",
        "security/ir.access.csv",
        "data/marketing_activity_data_templates_sms.xml",
    ],
    "auto_install": True,
    "uninstall_hook": "_uninstall_hook",
}
