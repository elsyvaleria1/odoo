{
    "name": "Calendar Synchronization",
    "version": "19.0.1.1.0",
    "category": "Productivity/Calendar",
    "summary": "Synchronize users' calendars with external providers through one engine",
    "description": "Keeps one synchronization account per user and provider: the delta token, the stop flag and the last synchronization, beside the user's own connection to the provider. Links each event and recurrence to its copy in each account's calendar, and keeps a deleted one's link until its copy is deleted. Runs every provider's synchronization from one scheduled action and one route, answers the calendar view's status and its start, stop and pause buttons for every installed provider, and lets a provider adapter (Google, Outlook) supply only what is particular to it. Installs with the calendar and integration modules; synchronizes nothing until an adapter is installed and a user authorizes it.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "calendar",
        "integration",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir_access_class.xml",
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "views/res_users_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "calendar_sync/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "calendar_sync/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
