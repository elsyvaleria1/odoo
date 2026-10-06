{
    "name": "Mail SMS Tests",
    "version": "1.0",
    "category": "Hidden",
    "sequence": 9876,
    "summary": "Test Mail SMS behaviour, including mail thread phone, phone blacklist, phone format",
    "description": "Run regression tests for Mail SMS. Loaded test suites include ``TestSMSActionsCommon``, ``TestPhoneBlacklist``, ``TestPhoneFormat``, ``TestSMSComposerComment``, ``TestSMSComposerBatch``.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "sms",
        "integration_twilio",
        "test_orm",
    ],
    "data": [
        "security/ir.access.csv",
    ],
}
