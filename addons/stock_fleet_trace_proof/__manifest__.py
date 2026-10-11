{
    "name": "Driver Screen: Customer's Code at the Door",
    "version": "19.0.1.0.0",
    "category": "Supply Chain/Inventory",
    "summary": "On the driver's phone, the customer at the door confirms a full delivery with a code sent to them",
    "description": "Adds to the Delivered form of the driver screen a step for the customer at the door: with signal, the driver sends them a code on their own channels (email, Telegram) and types the code they read out. The code proves the delivery as the customer received it, which then counts as its evidence: no photo of the slip, no drawn signature needed. Offered on full deliveries only: a code given before a partial one would vouch for what the customer did not take. Without signal the step is not shown and the driver captures the signature as before; the customer is asked on their own channels once the delivery reaches the server.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_fleet_proof",
        "stock_fleet_trace",
    ],
    "auto_install": True,
}
