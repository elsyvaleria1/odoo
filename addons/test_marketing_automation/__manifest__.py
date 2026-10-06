{
    "name": "Marketing Automation Tests",
    "version": "1.1",
    "category": "Hidden",
    "summary": "Test Marketing Automation behaviour, including activity triggers, data campaign, flow",
    "description": "Run regression tests for Marketing Automation. Loaded test suites include ``TestActivityTriggers``, ``TestDataCampaign``, ``TestMarketAutoFlow``, ``TestMassMailing``, ``MarketingCampaignTest``.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "marketing_automation",
        "marketing_automation_sms",
        "marketing_automation_whatsapp",
        "test_mail",
        "test_mail_enterprise",
        "test_mail_full",
        "test_mail_sms",
        "test_mass_mailing",
    ],
    "data": [
        "security/ir.access.csv",
    ],
}
