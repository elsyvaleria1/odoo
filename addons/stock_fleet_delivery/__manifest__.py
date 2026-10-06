{
    "name": "Carrier Dispatch Requirements",
    "version": "1.1",
    "category": "Supply Chain/Inventory",
    "summary": "Apply carrier dispatch modes to fleet-trip and tracking requirements",
    "description": "Adds own-fleet, salesperson, third-party and pickup modes to carriers and locations. Carrier mode takes precedence over source-location mode. For configured outgoing dispatch operations, third-party delivery requires a tracking reference; own-fleet and salesperson modes retain the inherited trip requirement.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "stock_fleet",
        "stock_delivery",
    ],
    "data": [
        "views/delivery_carrier_views.xml",
        "views/stock_picking_batch_views.xml",
    ],
    "auto_install": True,
}
