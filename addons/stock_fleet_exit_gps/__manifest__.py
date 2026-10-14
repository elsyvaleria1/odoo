{
    "name": "Vehicle Exits - GPS",
    "version": "19.0.1.0.0",
    "category": "Supply Chain/Inventory",
    "summary": "Routes read the odometer and the place where a vehicle stays from its GPS, and a vehicle leaving without a route raises an alert the authorisers hear of on Telegram",
    "description": "Bridges vehicle routes and the trip GPS sync. /rutas suggests the odometer the vehicle's GPS reads, and the name of the geofence the vehicle stands in when a route closes where the vehicle stays. A route out of the warehouse has its GPS exit and entry stamped, and entering the warehouse geofence closes it with the GPS odometer, as delivery trips do. Any vehicle leaving a warehouse that keeps a vehicle exit log with no departed trip raises a Left without an authorised route alert, naming the route still waiting for authorisation if there is one, and the vehicle exit authorisers with a linked Telegram chat are told at once with the time and a map link. Requires the trip GPS sync scheduled action, the warehouse coordinates, geofences for the places vehicles stay, and a GPS device linked to the vehicle.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "device_gps_geoengine",
        "stock_fleet_exit_telegram",
        "stock_fleet_trace_gps",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
    ],
    "auto_install": True,
}
