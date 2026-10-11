{
    "name": "Delivery Trips - GPS Readings",
    "version": "19.0.1.5.0",
    "category": "Supply Chain/Inventory",
    "summary": "Fill trip departure and return odometers from linked vehicle GPS data",
    "description": "Adds Read from GPS actions to delivery trips and vehicle helpers for odometer and fuel readings. Requires a linked GPS tracker with recent data; the odometer action also requires a valid positive odometer reading from the last two hours (system parameter asset_delivery_gps.trip_reading_max_age_minutes). Missing or stale data requires manual entry.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_fleet",
        "asset_gps",
    ],
    "data": [
        "views/stock_picking_batch_views.xml",
    ],
}
