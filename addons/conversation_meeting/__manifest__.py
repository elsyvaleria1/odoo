{
    "name": "Conversations - Meetings",
    "version": "19.0.2.2.0",
    "oldest_upgradable_version": "19.0.2.1.0",
    "category": "Sales/CRM",
    "sequence": 63,
    "summary": "Link calendar meetings to recordings, live coaching and minute exports",
    "description": "Starts or reopens conversations from calendar events and accepts room-device audio and chunks through authenticated routes. Adds live coaching notes using the configured analysis service and exports a Markdown minute from the conversation. Requires a configured meeting-room device, recording client, speech processing and model service access; the module does not supply room hardware.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "integration",
        "conversation",
        "device",
        "calendar",
        "bus",
    ],
    "data": [
        "security/security.xml",
        "security/ir.access.csv",
        "data/device_kind_data.xml",
        "views/calendar_event_views.xml",
        "views/conversation_conversation_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "conversation_meeting/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "conversation_meeting/static/tests/**/*",
        ],
    },
}
