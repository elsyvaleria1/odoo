{
    "name": "Delivery Trips - GPS Track Map",
    "version": "19.0.1.4.0",
    "category": "Supply Chain/Inventory",
    "summary": "See on a map the road a delivery trip travelled, with its stops, deliveries, incidents and alerts",
    "description": "Adds a View GPS Track button to delivery trips: it draws the vehicle's GPS trail between departure and return on the trail map, with the trip's planned stops, what happened at each (arrival, delivery, not delivered), the incidents and the GPS alerts marked where they happened. The printed trip sheet carries the same as a route map, with each stop numbered as the sheet sequences it.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_fleet_trace_gps",
        "device_gps_geoengine",
    ],
    "data": [
        "security/stock_fleet_trace_gps_geoengine_security.xml",
        "security/ir.access.csv",
        "security/ir_access.xml",
        "views/stock_picking_batch_views.xml",
        "views/wizard_stock_trip_track_point_views.xml",
        "data/geoengine_vector_layer_data.xml",
        "reports/report_picking_batch.xml",
    ],
    "auto_install": True,
}
