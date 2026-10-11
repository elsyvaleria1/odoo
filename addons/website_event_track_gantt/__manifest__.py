{
    "name": "Event Track Gantt",
    "version": "1.0",
    "category": "Marketing",
    "summary": "Schedule event tracks by location in a Gantt view",
    "description": "Add a Gantt view to event tracks with start and end times and location grouping. The embedded track form provides actions for rescheduling and removing tracks.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_event_track",
        "web_gantt",
    ],
    "data": [
        "views/event_event_views.xml",
        "views/event_track_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "website_event_track_gantt/static/src/**/*.js",
        ],
    },
    "auto_install": True,
}
