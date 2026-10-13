{
    "name": "Carrier Tracking Status",
    "version": "19.0.1.2.0",
    "oldest_upgradable_version": "19.0.1.0.0",
    "category": "Supply Chain/Inventory",
    "summary": "Consult carrier status, shipment history and documents on transfers",
    "description": "Adds carrier status and a Shipment Tracking tab to transfers. Reads each tracking number once per carrier, retains shipment details and movement history, and links to documents published by the carrier. A transfer with several numbers is delivered only when all numbers report delivery. Failed reads retain the last successful result; changing the carrier or numbers clears the old tracking data. Operation types can opt in selected carriers to validate ready outgoing transfers after delivery, preserving normal stock checks. Blocked deliveries retain an error and activity and are retried by the scheduled action. Other transfers retain manual validation with a delivery to-do. Connectors supply the data and permit document links; this module reads nothing on its own.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_delivery",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "data/mail_activity_type_data.xml",
        "views/delivery_carrier_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_picking_type_views.xml",
    ],
}
