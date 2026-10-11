{
    "name": "Field Service Worksheets and Reports",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Services/Field Service",
    "summary": "Complete task worksheets and include their contents in field service reports",
    "description": "Adds project and task worksheet templates, worksheet forms, report rendering and portal report context. Requires worksheets enabled on the project and a task template; report rendering selects the latest worksheet linked to the task.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "worksheet",
        "industry_fsm",
        "web_studio",
    ],
    "data": [
        "security/ir.access.csv",
        "views/project_project_views.xml",
        "views/project_portal_project_task_templates.xml",
        "views/project_task_views.xml",
        "views/worksheet_template_views.xml",
        "views/res_config_settings_views.xml",
        "reports/project_task_burndown_chart_report_views.xml",
        "reports/report_industry_fsm_worksheet_custom_templates.xml",
        "data/worksheet_template_data.xml",
        "wizards/wizard_project_task_create_worksheet_template_views.xml",
        "views/industry_fsm_report_menus.xml",
    ],
    "demo": [
        "demo/worksheet_template_demo.xml",
        "demo/project_task_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "industry_fsm_report/static/src/js/tours/industry_fsm_report_tour.js",
        ],
        "web.assets_frontend": [
            "industry_fsm_report/static/src/js/tours/industry_fsm_report_tour.js",
        ],
        "web.assets_tests": [
            "industry_fsm_report/static/tests/tours/**/*",
        ],
    },
    "auto_install": [
        "industry_fsm",
        "web_studio",
    ],
    "post_init_hook": "post_init",
}
