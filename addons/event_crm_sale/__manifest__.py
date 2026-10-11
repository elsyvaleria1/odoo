{
    "name": "Event Sales Lead Grouping",
    "version": "1.0",
    "category": "Marketing/Events",
    "summary": "Group event-generated leads using their sales order",
    "description": "Extend event lead generation with the registration's linked sales order. Uses that order when determining lead grouping.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/events",
    "license": "Other OSI approved licence",
    "depends": [
        "event_crm",
        "event_sale",
    ],
    "data": [
        "views/event_lead_rule_views.xml",
    ],
    "auto_install": True,
}
