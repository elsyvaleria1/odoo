{
    "name": "Shipping Orders over Telegram",
    "version": "19.0.1.0.0",
    "category": "Supply Chain/Inventory",
    "summary": "Send a carrier's shipping order from Telegram and put its tracking number on the transfer",
    "description": "Adds the /embarque bot command: whoever hands a shipment to a parcel carrier sends the photo or PDF of the shipping order the carrier gave them. The tracking number is read from the sheet's barcode, or its text, and recognised by a carrier's tracking number pattern; route, service and amounts are read with it. The sender chooses the delivery order, or the receipt when the carrier brings a purchase, among the open ones of that carrier; the tracking number and the carrier go on it, and the sheet is kept on its chatter. A tracking number is never written over a different one. Other modules hook in when a sheet is assigned, to prepare the freight request. Requires a linked Telegram account and write access to transfers.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "extract_delivery",
        "stock_fleet_telegram",
    ],
    "data": [
        "security/ir.access.csv",
        "data/telegram_command_data.xml",
    ],
}
