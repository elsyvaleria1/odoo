{
    "name": "WhatsApp Job Referrals",
    "version": "1.0",
    "category": "Human Resources/Referrals",
    "sequence": 236,
    "summary": "Share employee job-referral links through WhatsApp",
    "description": "Adds a job action and referral message template for the WhatsApp composer. Requires a configured WhatsApp account and recipient number.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_referral",
        "whatsapp",
    ],
    "data": [
        "views/hr_job_views.xml",
        "data/whatsapp_template_data.xml",
    ],
    "auto_install": True,
}
