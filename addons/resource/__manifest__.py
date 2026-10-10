{
    "name": "Resource Scheduling",
    "version": "1.40",
    "category": "Hidden",
    "summary": "Manage resource calendars, availability, reservations and physical assets",
    "description": "Provide schedulable resources, working calendars and reservation models. Applications use the scheduling mixins to reserve resources over time intervals. A physical asset is a resource of a kind, with identifiers, meters, custody and components; specialized addons extend each kind in a model of its own.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "web",
        "uom",
    ],
    "data": [
        "data/resource_data.xml",
        "data/resource_identifier_type_data.xml",
        "data/resource_kind_data.xml",
        "security/resource_security.xml",
        "security/ir.access.csv",
        "security/ir_access.xml",
        "views/resource_reservation_views.xml",
        "views/resource_assignment_views.xml",
        "views/resource_relation_views.xml",
        "views/resource_kind_views.xml",
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
