{
    "name": "Field Collections over Telegram",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Collectors record what customers paid them, see their custody and hand it in from Telegram",
    "description": "Adds three bot commands for collectors: /cobro records a customer's cash or check payment against their open invoices on the day it was paid, with a photo of the receipt; /custodia lists the collections the collector still holds; /rendir hands them in to a till or a bank account with the deposit slip, as a remittance the treasury validates. Requires a linked Telegram account, the Collector group and a collection custody journal in the collector's company.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "account_collection",
        "telegram",
    ],
    "data": [
        "data/telegram_command_data.xml",
    ],
}
