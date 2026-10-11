{
    "name": "Event Gantt, Map and Cohort Views",
    "category": "Marketing/Events",
    "summary": "Display event schedules and venues and analyze registration cohorts",
    "description": "Adds Gantt and venue map views to events and cohort views to registrations. Cohorts use event begin dates and registration creation dates; view rendering and map services are supplied by the declared web dependencies.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "event",
        "web_cohort",
        "web_gantt",
        "web_map",
    ],
    "data": [
        "views/event_event_views.xml",
        "views/event_registration_views.xml",
    ],
    "auto_install": True,
}
