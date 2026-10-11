{
    "name": "Telegram for Live Chat",
    "version": "19.0.1.0.0",
    "category": "Website/Live Chat",
    "summary": "Customers write to a Telegram bot and are answered from Live Chat",
    "description": "A person who is not an Odoo user writing to a Telegram bot linked to a Live Chat channel opens a live chat session: operator routing, the channel's chatbot, looking-for-help, ratings, reports and the /lead and /ticket commands apply as for a website visitor. Operators answer from Odoo -- or from their own Telegram through the personal bridge -- and their messages reach the customer's Telegram. A message that finds no operator online still opens a session, looking for help, and the customer is told when to expect an answer.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "im_livechat",
        "mail_telegram",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "views/telegram_bot_views.xml",
    ],
    "auto_install": True,
}
