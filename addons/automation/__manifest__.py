{
    "name": "Automation Rules",
    "version": "1.14",
    "oldest_upgradable_version": "1.13",
    "category": "Sales/Sales",
    "summary": "Trigger configured actions and workflows from business-record events",
    "description": "Define automation rules and workflow steps for business models. Rules select the triggering events, matching records and actions to execute.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "bus",
        "digest",
        "mail",
        "resource",
        "sms",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "data/digest_data.xml",
        "data/ir_sequence_data.xml",
        "views/automation_rule_views.xml",
        "views/automation_runtime_views.xml",
        "views/automation_runtime_line_views.xml",
        "views/ir_actions_server_views.xml",
        "views/workflow_dag_views.xml",
        "views/automation_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "automation/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "automation/static/tests/**/*",
        ],
    },
}
