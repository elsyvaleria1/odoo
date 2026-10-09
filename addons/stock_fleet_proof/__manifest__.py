{
    "name": "Deliveries Confirmed by the Customer",
    "version": "19.0.1.0.0",
    "category": "Supply Chain/Inventory",
    "summary": "The customer confirms on their own phone or email the goods a delivery left them",
    "description": "A delivery whose operation type requires the signed slip asks its customer, once validated (an offline driver's event included, once it reaches the server), to confirm on every channel that reaches them what it left: the products and quantities, the day, the driver, the reference. They answer Confirm or Not right there; the answer is chained as proof evidence on the delivery, and noted on it in their name. A confirmation counts as the delivery's evidence beside the photo of the signed slip and the signature: proven at the door with a code sent to the customer, it lets the delivery be validated without the photo; given later, it ticks the evidence valid once, which a reviewer may take back. Not right puts an activity on the delivery's responsible; a delivery nobody answers is only noted, and its status stays visible to the reviewers.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "proof",
        "stock_fleet",
    ],
    "data": [
        "security/stock_fleet_proof_security.xml",
        "views/stock_picking_views.xml",
    ],
}
