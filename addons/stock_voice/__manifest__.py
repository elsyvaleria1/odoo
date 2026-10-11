{
    "name": "Inventory Voice Button Phrases",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Add spoken aliases for the transfer Validate buttons",
    "description": "Adds delivery, transfer and receipt completion phrases to the stock transfer form validation buttons. Recognition and command execution come from the voice dependency; stock validation retains its existing checks and any follow-up dialogs.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "voice",
        "stock",
    ],
    "data": [
        "views/stock_picking_views.xml",
    ],
    "auto_install": True,
}
