{
    "name": "Resource Scheduling",
    "version": "1.39",
    "category": "Hidden",
    "summary": "Manage resource calendars, availability and reservations",
    "description": "Provide schedulable resources, working calendars and reservation models. Applications use the scheduling mixins to reserve resources over time intervals.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "web",
        "uom",
    ],
    "data": [
        "data/resource_data.xml",
        "data/resource_identifier_type_data.xml",
        "security/resource_security.xml",
        "security/ir.access.csv",
        "views/resource_reservation_views.xml",
        "views/resource_assignment_views.xml",
        "views/resource_relation_views.xml",
        "views/resource_resource_views.xml",
        "views/resource_role_views.xml",
        "views/resource_identifier_type_views.xml",
        "views/resource_meter_views.xml",
        "views/resource_schedule_exception_views.xml",
        "views/resource_calendar_attendance_views.xml",
        "views/resource_calendar_views.xml",
        "views/menuitems.xml",
    ],
    "demo": [
        "demo/resource_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "resource/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "resource/static/tests/**/*",
        ],
    },
}
