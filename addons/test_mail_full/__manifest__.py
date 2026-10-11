{
    "name": "Mail Integration Tests",
    "version": "1.0",
    "category": "Hidden",
    "sequence": 9876,
    "summary": "Test Mail Integration behaviour, including controller attachment, controller reaction, controller update",
    "description": "Run regression tests for Mail Integration. Loaded test suites include ``TestPortalAttachmentController``, ``TestPortalMessageReactionController``, ``TestPortalMessageUpdateController``, ``TestPortalThreadController``, ``TestIrMailServerPersonal``.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
        "mail_bot",
        "portal",
        "rating",
        "mass_mailing",
        "mass_mailing_sms",
        "phone_validation",
        "sms",
        "test_mail",
        "test_mail_sms",
        "test_mass_mailing",
    ],
    "data": [
        "data/mail_message_subtype_data.xml",
        "security/ir.access.csv",
        "views/test_portal_template.xml",
    ],
    "assets": {
        "web.assets_unit_tests": [
            "test_mail_full/static/tests/**/*",
            (
                "remove",
                "test_mail_full/static/tests/tours/**/*",
            ),
        ],
        "web.assets_tests": [
            "test_mail_full/static/tests/tours/**/*",
        ],
    },
}
