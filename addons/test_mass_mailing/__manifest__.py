{
    "name": "Mass Mailing Tests",
    "version": "1.0",
    "category": "Marketing/Email Marketing",
    "sequence": 8765,
    "summary": "Test Mass Mailing behaviour, including blacklist, blacklist behavior, blacklist mixin",
    "description": "Run regression tests for Mass Mailing. Loaded test suites include ``TestBLAccessRights``, ``TestBLConsistency``, ``TestAutoBlacklist``, ``TestBLMixin``, ``TestLinkTracker``.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mass_mailing",
        "mass_mailing_sms",
        "sms_twilio",
        "test_mail",
        "test_mail_sms",
    ],
    "data": [
        "security/ir.access.csv",
    ],
}
