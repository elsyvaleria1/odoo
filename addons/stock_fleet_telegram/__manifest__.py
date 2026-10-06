{
    "name": "Trips over Telegram",
    "version": "19.0.1.0.0",
    "category": "Supply Chain/Inventory",
    "summary": "Whoever delivered sends the photo of the signed delivery slip from Telegram",
    "description": "Adds the /entrega bot command: the driver or salesperson who delivered sends the photo of the delivery slip the customer signed. The bot reads the slip's QR code, or offers the deliveries waiting for it, files the photo as the delivery's signed slip and, when the delivery rides a departed trip of theirs, marks it delivered. Requires a linked Telegram account and the Driver group.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "extract_barcode",
        "stock_fleet",
        "telegram",
    ],
    "data": [
        "data/telegram_command_data.xml",
    ],
}
