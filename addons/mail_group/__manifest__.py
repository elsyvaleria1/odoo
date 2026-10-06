{
    "name": "Mailing Groups",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Productivity/Discuss",
    "summary": "Manage mailing-list membership, conversations and moderation",
    "description": "Adds mailing groups, members, threaded messages and moderation decisions. Provides subscription and unsubscribe routes and message archives with group-specific access rules. Email distribution uses the mail infrastructure and its configured delivery transport.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "portal",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "data/mail_templates.xml",
        "data/mail_template_data.xml",
        "data/mail_template_email_layouts.xml",
        "data/res_groups.xml",
        "security/ir.access.csv",
        "wizards/wizard_mail_group_message_reject_views.xml",
        "views/mail_compose_message_views.xml",
        "views/mail_group_member_views.xml",
        "views/mail_group_message_views.xml",
        "views/mail_group_moderation_views.xml",
        "views/mail_group_views.xml",
        "views/mail_group_menus.xml",
        "views/portal_templates.xml",
    ],
    "demo": [
        "demo/mail_group_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "mail_group/static/src/css/mail_group.scss",
            "mail_group/static/src/interactions/*",
        ],
        "web.assets_backend": [
            "mail_group/static/src/css/mail_group_backend.scss",
        ],
    },
}
