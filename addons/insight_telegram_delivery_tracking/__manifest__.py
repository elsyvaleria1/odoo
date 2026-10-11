{
    "name": "Telegram Questions About Carrier Tracking",
    "version": "19.0.1.1.0",
    "oldest_upgradable_version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Consult shipment status by tracking number from a linked Telegram account",
    "description": "Adds /rastreo to selected Telegram bots, without enabling AI questions. A linked internal user in a private chat reads shipments using their own Odoo permissions and the companies they share with the bot. Complete tracking numbers match exactly, including transfers with several numbers. The answer reports the saved status and its read date, and explains missing reads or failed refreshes. Reuses the tracking report also available to the separate questions bot. Reads only: it does not call carriers, change shipments or validate deliveries.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "insight_telegram",
        "delivery_tracking",
    ],
    "data": [
        "data/telegram_command_data.xml",
    ],
    "auto_install": True,
}
