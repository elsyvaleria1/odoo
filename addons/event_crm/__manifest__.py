{
    "name": "Event Lead Generation",
    "version": "1.0",
    "category": "Marketing/Events",
    "summary": "Generate CRM leads from event registrations",
    "description": "Define lead-generation rules for event registrations and run them manually or on a schedule. Rules select the registrations and lead assignment information.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/events",
    "license": "Other OSI approved licence",
    "depends": [
        "event",
        "crm",
    ],
    "data": [
        "security/ir.access.csv",
        "data/crm_lead_merge_template.xml",
        "data/ir_action_data.xml",
        "data/ir_cron_data.xml",
        "views/crm_lead_views.xml",
        "views/event_registration_views.xml",
        "views/event_lead_rule_views.xml",
        "views/event_event_views.xml",
        "views/event_question_views.xml",
        "views/event_crm_menus.xml",
    ],
    "demo": [
        "demo/event_crm_demo.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "event_crm/static/tests/tours/*.js",
        ],
    },
    "auto_install": True,
}
