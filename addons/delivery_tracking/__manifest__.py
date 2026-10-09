{
    "name": "Carrier Tracking Status",
    "version": "19.0.1.0.0",
    "oldest_upgradable_version": "19.0.1.0.0",
    "category": "Supply Chain/Inventory",
    "summary": "Read the status of carrier tracking numbers into transfers",
    "description": "Adds the carrier's last reported status to transfers that carry a tracking number: a normalized state (in transit, at destination, out for delivery, delivered), the raw event, branch and date, home delivery or pickup, the estimated delivery and who received it. A scheduled action reads every open number once per carrier and number, posts each change in the chatter and gives the responsible a to-do when an open transfer is delivered; it never validates a transfer. Carrier connectors register themselves as tracking providers; this module reads nothing on its own.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "stock_delivery",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "views/delivery_carrier_views.xml",
        "views/stock_picking_views.xml",
    ],
}
