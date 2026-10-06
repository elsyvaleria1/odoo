{
    "name": "Email Inboxes in Discuss",
    "version": "1.0",
    "category": "Productivity/Discuss",
    "summary": "Read and answer the mail sent to a person's or a team's address in Discuss",
    "description": "An inbox is an email address served by Odoo, for one person or a team. Mail sent to it arrives as a Discuss conversation in the Email tab, one per correspondent, whose members are the inbox's users and the sender; a reply written there is sent by email from the inbox's address, threaded with the messages it answers, and the correspondent's next reply lands in the same conversation. Requires the address to be routed to Odoo (an incoming mail server and an alias domain).",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "mail",
    ],
    "data": [
        "security/ir.access.csv",
        "data/mail_templates_email_layouts.xml",
        "views/mail_inbox_views.xml",
        "views/mail_inbox_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mail_inbox/static/src/core/**/*",
        ],
        "web.assets_unit_tests": [
            "mail_inbox/static/tests/**/*",
        ],
        "im_livechat.embed_assets_unit_tests": [
            "mail_inbox/static/tests/mock_server/**/*",
        ],
    },
}
