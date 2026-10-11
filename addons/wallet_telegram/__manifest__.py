{
    "name": "Wallets over Telegram",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Cardholders consult dated balances and request top-ups through Telegram",
    "description": "Adds /saldo and /recarga to a configured Telegram bot. Linked internal users see only active cards whose holder is their own contact, within the wallet accounts and companies the bot serves. Balances show the date of the last issuer observation; an unobserved balance is reported as unavailable. A guided top-up request collects a card, amount and reason, and creates a native approval request only after confirmation. Approval routing comes from the category configured on each wallet account. These commands do not transfer money, create issuer funding instructions or refresh issuer balances.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "approval_telegram",
        "wallet",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "data/telegram_command_data.xml",
        "views/telegram_bot_views.xml",
        "views/wallet_account_views.xml",
    ],
}
