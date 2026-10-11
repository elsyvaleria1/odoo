{
    "name": "Trips over Telegram",
    "version": "19.0.1.2.0",
    "category": "Supply Chain/Inventory",
    "summary": "Whoever delivered sends the signed delivery slips from Telegram, and administration receives the papers in batches",
    "description": "Adds the /entrega bot command: whoever delivered sends the photos or PDFs of the delivery slips the customer signed, one after another, and presses Finish. Each file is read for its delivery order: a code printed on the slip carrying its name or, without one, the delivery number printed on the paper together with the customer's name or RFC, read from its text layer or by local OCR; unidentified, the sender chooses among their deliveries waiting for the slip. The file becomes the delivery's signed slip, kept as sent on its chatter. A delivery on the departed trip the sender drives is marked delivered as the trip's Delivered button does; any other keeps the slip and stays for whoever validates it, and a validation that does not go through keeps the slip and says why. Finish hands the chat's slips to administration as a batch under Inventory, Delivery Slip Reception, where a reviewer removes the papers that did not arrive and confirms, which ticks Received on Paper on each delivery and prints the reception receipt with its folio. Requires a linked Telegram account and write access to transfers.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "extract_barcode",
        "extract_ocr",
        "stock_fleet",
        "telegram",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "data/telegram_command_data.xml",
        "reports/report_delivery_slip_receipt.xml",
        "views/stock_delivery_slip_receipt_views.xml",
        "views/stock_fleet_telegram_menus.xml",
    ],
}
