{
    "name": "Telegram Approvals",
    "version": "19.0.2.1.0",
    "oldest_upgradable_version": "19.0.2.1.0",
    "category": "Human Resources/Approvals",
    "summary": "Keep Telegram-captured data on approval requests, and review and decide them through Telegram buttons and a Mini App",
    "description": "Adds configured approver notifications, approve/refuse/change-request actions and a Mini App for pending requests and owner corrections. Resolves decisions to linked internal users and the existing approval records. Requires a configured bot, enabled notification settings and linked user chats; delivery depends on Telegram access.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "telegram",
        "approval",
        "approval_product",
    ],
    "data": [
        "views/approval_request_views.xml",
        "views/approval_category_step_views.xml",
        "views/telegram_bot_views.xml",
        "views/miniapp_templates.xml",
    ],
}
