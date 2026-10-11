{
    "name": "ORM Tests",
    "version": "1.0",
    "category": "Hidden/Tests",
    "summary": "Test ORM behaviour, including access scope, attributes, autovacuum",
    "description": "Run regression tests for ORM. Loaded test suites include ``TestX2manyScopeFollowsWhatTheRulesRead``, ``TestComputedX2manyUserScope``, ``TestAttributes``, ``TestAutovacuum``, ``TestBackendDifferential``.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "base",
        "web",
        "web_tour",
    ],
    "data": [
        "security/ir.access.csv",
        "views/test_orm_views.xml",
        "data/test_orm_data.xml",
        "views/test_orm_menus.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "test_orm/static/tests/tours/constraint.js",
            "test_orm/static/tests/tours/x2many.js",
        ],
    },
}
