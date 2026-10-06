{
    "name": "Live Event Talk Pages",
    "version": "1.0",
    "category": "Marketing/Events",
    "sequence": 1006,
    "summary": "Embed live video and chat in event talk pages",
    "description": "Adds live-broadcast settings and website components for configured talk videos and chat. The external video stream must be supplied by the event organizer.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/events",
    "license": "LGPL-3",
    "depends": [
        "website_event_track",
    ],
    "data": [
        "views/event_track_templates_list.xml",
        "views/event_track_templates_page.xml",
        "views/event_track_views.xml",
    ],
    "demo": [
        "demo/event_track_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_event_track_live/static/src/scss/website_event_track_live.scss",
            "website_event_track_live/static/src/interactions/*.js",
            "website_event_track_live/static/src/xml/**/*",
        ],
    },
}
