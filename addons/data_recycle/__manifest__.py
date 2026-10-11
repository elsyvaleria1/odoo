{
    "name": "Record Recycling Rules",
    "version": "1.6",
    "oldest_upgradable_version": "1.6",
    "category": "Productivity/Data Cleaning",
    "summary": "Find records to archive or delete using configured rules",
    "description": "Provides model-specific selection domains, reviewable candidate records and scheduled processing. Rules select archive or deletion and manual or automatic execution.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "views/data_recycle_model_views.xml",
        "views/data_recycle_record_views.xml",
        "views/data_cleaning_menu.xml",
        "views/data_recycle_templates.xml",
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "data_recycle/static/src/views/*.js",
            "data_recycle/static/src/views/*.xml",
        ],
        "web.assets_tests": [
            "data_recycle/static/tests/tours/*.js",
        ],
    },
    "application": True,
}
