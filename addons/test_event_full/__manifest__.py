{
    "name": "Event Integration Tests",
    "version": "1.0",
    "category": "Hidden/Tests",
    "summary": "Test Event Integration behaviour, including event crm, event event, event mail",
    "description": "Run regression tests for Event Integration. Loaded test suites include ``TestEventCrm``, ``TestEventEvent``, ``TestEventMailInternals``, ``TestEventMailSchedule``, ``TestEventSaleMail``.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "event",
        "event_booth",
        "event_crm",
        "event_crm_sale",
        "event_sale",
        "event_sms",
        "payment_demo",
        "website_event_booth_sale_exhibitor",
        "website_event_exhibitor",
        "website_event_sale",
        "website_event_track",
        "website_event_track_live",
        "website_event_track_quiz",
    ],
    "data": [
        "data/ir_actions_report_data.xml",
        "views/event_registration_templates_reports.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "test_event_full/static/src/js/tours/*",
        ],
        "web.assets_unit_tests": [
            "test_event_full/static/tests/*",
        ],
    },
}
