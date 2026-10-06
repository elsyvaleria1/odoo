{
    "name": "Field Collections, Sales and Traced Trips",
    "version": "19.0.1.0.0",
    "category": "Supply Chain/Inventory",
    "summary": "A cash sale handed over on the route takes its goods from the stock the salesperson's vehicle carries to sell",
    "description": "When a salesperson on a departed traced trip collects a cash sale whose customer takes the goods at once, and the vehicle carries enough unreserved stock of every product of the order, the delivery leaves from the vehicle's location and counts as delivered in the trip's balance. Otherwise it leaves from the warehouse, as a counter pickup. What the vehicle does not sell comes back with the trip's unloading.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "account_collection_sale_fleet",
        "stock_fleet_trace",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "auto_install": True,
}
