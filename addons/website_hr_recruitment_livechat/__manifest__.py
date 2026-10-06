{
    "name": "Recruitment Chatbot Demo",
    "version": "1.0",
    "category": "Website/Live Chat",
    "summary": "Load a sample jobs-page chatbot when demo data is enabled",
    "description": "Provides a demonstration live chat rule and scripted recruitment questions for the jobs page. The addon loads only demo records and supplies no independent production chatbot engine; recruitment and live chat behavior come from its dependencies.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website_hr_recruitment",
        "im_livechat",
    ],
    "demo": [
        "demo/website_hr_recruitment_livechat_chatbot_demo.xml",
    ],
}
