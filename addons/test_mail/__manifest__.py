{
    "name": "Mail Tests",
    "version": "1.0",
    "category": "Hidden",
    "sequence": 9876,
    "summary": "Test Mail behaviour, including base id spaces, controller attachment, controller binary",
    "description": "Run regression tests for Mail. Loaded test suites include ``TestBaseIdSpaces``, ``TestBaseSuggestedMessageSort``, ``TestAttachmentController``, ``TestPublicBinaryController``, ``TestMessageController``.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
        "test_orm",
    ],
    "data": [
        "security/ir.access.csv",
        "data/data.xml",
        "data/mail_template_data.xml",
        "data/subtype_data.xml",
    ],
    "assets": {
        "web.assets_unit_tests": [
            "test_mail/static/tests/**/*",
        ],
        "web.assets_tests": [
            "test_mail/static/tests/tours/*",
        ],
    },
}
