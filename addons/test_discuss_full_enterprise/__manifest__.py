{
    "name": "Enterprise Discuss Integration Tests",
    "category": "Hidden",
    "summary": "Test Enterprise Discuss Integration behaviour, including ai draft ui",
    "description": "Run regression tests for Enterprise Discuss Integration. Loaded test suites include ``TestAIDraftUI``.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "ai",
        "account",
        "document",
        "knowledge",
        "sign",
        "test_discuss_full",
        "voip",
        "voip_onsip",
        "website_helpdesk_livechat",
        "web_studio",
        "whatsapp",
    ],
    "assets": {
        "web.assets_tests": [
            "test_discuss_full_enterprise/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "test_discuss_full_enterprise/static/tests/*",
        ],
    },
    "auto_install": [
        "test_discuss_full",
    ],
}
