{
    "name": "Field Collections over Telegram, Confirmed by the Customer",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "After /cobro, the collector sees whether the customer was asked, confirms with the customer's code, or invites them to Telegram",
    "description": "Once /cobro records a collection, the bot tells the collector where its customer was asked to confirm it, instead of where a receipt went. With the customer at hand, Customer is here sends them a code and the collector types it into the chat; the code proves the collection as the form's button does. A customer no channel reaches can be invited: the bot sends the collector a QR the customer scans with their own phone, which connects their Telegram, and the question then reaches them there. The evidence of an answer through a connection made this way names who invited it.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "account_collection_proof",
        "account_collection_telegram",
        "telegram_proof",
    ],
    "auto_install": True,
}
