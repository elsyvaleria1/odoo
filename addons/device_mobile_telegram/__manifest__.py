{
    "name": "Telegram on Company Phones",
    "version": "19.0.1.0.0",
    "category": "Productivity/Discuss",
    "summary": "Let a bot deliver Odoo notifications only to the Telegram of a company phone assigned to its user",
    "description": "A bot delivering Odoo notifications can be restricted to company phones: a user's notifications, replies and inbox then reach only a Telegram account whose number, shared by its owner and vouched for by Telegram, is the SIM number of an active Mobile Phone device the user carries. A connected account without a shared number is asked for it. The device form shows the Telegram account of the phone's number and who it acts as.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "device_mobile",
        "mail_telegram",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir_access_class.xml",
        "security/ir.access.csv",
        "views/telegram_bot_views.xml",
        "views/device_device_views.xml",
    ],
    "auto_install": True,
}
