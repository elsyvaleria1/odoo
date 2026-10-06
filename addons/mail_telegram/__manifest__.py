{
    "name": "Telegram for Discuss and Chatter",
    "version": "19.0.1.3.0",
    "oldest_upgradable_version": "19.0.1.3.0",
    "category": "Productivity/Discuss",
    "summary": "Deliver a connected user's Odoo notifications and chats to their Telegram, and post their Telegram replies back",
    "description": "A user who connected Telegram (Preferences) receives their inbox notifications, direct and group chats and channel mentions in Telegram, each with a link back to Odoo and a Mark as Read button, according to preferences that say always, only while away, or never. Nothing already read in Odoo is sent: delivery waits a grace period and checks again. Replying to one of those messages in Telegram posts the reply on the same record or conversation as that user, under their access rights; a reply to an internal note stays a note, and a reply that would reach external followers asks first. Requires a bot with Deliver Odoo Notifications enabled. A Telegram group, connected with a link made in Odoo, is a Telegram channel of Discuss: its people's messages are posted there as their contacts, forum topics are sub-channels, and what Odoo users write goes to the group under their names.",
    "author": "AgroMarin",
    "license": "OPL-1",
    "depends": [
        "mail",
        "telegram",
    ],
    "data": [
        "security/ir_access_class.xml",
        "security/ir.access.csv",
        "views/res_users_views.xml",
        "views/telegram_bot_views.xml",
        "views/wizard_telegram_group_link_views.xml",
        "views/telegram_mirror_views.xml",
        "views/mail_telegram_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mail_telegram/static/src/core/common/**/*",
            "mail_telegram/static/src/core/public_web/**/*",
            "mail_telegram/static/src/discuss/core/public_web/**/*",
        ],
        "web.assets_unit_tests": [
            "mail_telegram/static/tests/**/*",
        ],
        "im_livechat.embed_assets_unit_tests": [
            "mail_telegram/static/tests/mock_server/**/*",
        ],
    },
    "auto_install": True,
}
