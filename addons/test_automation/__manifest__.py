{
    "name": "Automation Tests",
    "version": "1.1",
    "category": "Hidden",
    "sequence": 9877,
    "summary": "Test Automation behaviour, including flow, server actions, tour",
    "description": "Run regression tests for Automation. Loaded test suites include ``AutomationRuleTest``, ``TestCompute``, ``TestHttp``, ``TestServerActionsValidation``, ``TestOnUnlinkWarnsForActionsNeedingTheirRecord``.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "automation",
        "automation_webhook",
        "test_mail",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_tests": [
            "test_automation/static/tests/**/*",
        ],
    },
    "post_init_hook": "_post_init_hook",
}
