{
    "name": "Website Event Lead Details",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Add website registration details to event-generated CRM leads",
    "description": "Extend the lead description and preparation values from website event registration information. Uses the event lead-generation rules supplied by its dependencies.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/events",
    "license": "LGPL-3",
    "depends": [
        "event_crm",
        "website_event",
    ],
    "data": [
        "views/event_lead_rule_views.xml",
    ],
    "demo": [
        "demo/event_crm_demo.xml",
    ],
    "auto_install": True,
}
