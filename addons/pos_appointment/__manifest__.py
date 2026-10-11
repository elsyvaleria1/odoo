{
    "name": "POS Appointment Bookings",
    "version": "1.1",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Review and manage appointment bookings from the POS",
    "description": "Loads bookings for the configured appointment type into the POS and supplies booking details, status actions and links to booking forms and timelines.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/appointments",
    "license": "Other OSI approved licence",
    "depends": [
        "calendar",
        "point_of_sale",
        "calendar_gantt",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/calendar_event_views.xml",
    ],
    "assets": {
        "pos_appointment.html_editor": [
            (
                "include",
                "html_editor._assets_editor",
            ),
            "html_editor/static/src/others/dynamic_placeholder_plugin.js",
            "html_editor/static/src/main/placeholder_plugin.js",
            "html_editor/static/src/backend/**/*",
            (
                "remove",
                "html_editor/static/src/utils/regex.js",
            ),
            "html_editor/static/src/fields/html_field*",
        ],
        "point_of_sale._assets_pos": [
            (
                "include",
                "pos_appointment.html_editor",
            ),
            "web_gantt/static/src/**/*",
            "pos_appointment/static/src/**/*",
            "calendar/static/src/booking/components/appointment_booking_action_helper/*",
            "calendar/static/src/booking/components/appointment_type_sync_duration/*",
            "calendar_gantt/static/src/**/*",
            "calendar/static/src/booking/xml/appointment_svg.xml",
            "calendar/static/src/scss/calendar_event_views.scss",
            "calendar/static/src/views/**/*",
        ],
        "web.assets_unit_tests_setup": [
            "html_editor/static/src/utils/regex.js",
        ],
        "web.assets_unit_tests": [
            "pos_appointment/static/tests/unit/**/*",
        ],
    },
}
