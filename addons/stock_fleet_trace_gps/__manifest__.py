{
    "name": "Delivery Trips - GPS Traceability",
    "version": "19.0.1.1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Stamp trip departures, stops and returns from the vehicle's GPS track and raise alerts on what the track contradicts",
    "description": "Reads the GPS history of each delivery vehicle. Leaving the warehouse geofence departs its loaded trip with the GPS odometer and fuel, and a delivery vehicle leaving without one raises an alert. Dwelling at a customer's location verifies the stop; an outcome the track never visited, an unplanned stop, harsh driving, refuelling and a silent GPS are recorded on the trip. Entering the warehouse geofence records the return readings and closes the trip once every stop has its outcome. The GPS times date the departure and the return, and the kilometres of each leg follow the stops the track verified, not delivered ones included. Requires warehouse and customer coordinates and a GPS device linked to the vehicle.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_fleet_trace",
        "asset_delivery_gps",
    ],
    "data": [
        "security/stock_fleet_trace_gps_security.xml",
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "views/stock_trip_alert_views.xml",
        "views/stock_warehouse_views.xml",
        "views/stock_picking_batch_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_fleet_trace_gps_menus.xml",
    ],
}
