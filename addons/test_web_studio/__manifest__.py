{
    "name": "Web Studio Tests",
    "version": "1.0",
    "category": "Hidden",
    "sequence": 9876,
    "summary": "Test Web Studio behaviour, including approvals, approval activity, exports",
    "description": "Run regression tests for Web Studio. Loaded test suites include ``TestStudioApprovals``, ``TestStudioApprovalsUIUnit``, ``TestApprovalsActivity``, ``TestStudioExports``, ``TestSpecificStudioExports_SaleOrder``.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "web_studio",
        "website",
        "sale",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_tests": [
            "test_web_studio/static/tests/**/*",
        ],
    },
}
