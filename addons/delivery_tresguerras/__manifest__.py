{
    "name": "Tres Guerras Tracking",
    "version": "19.0.1.1.0",
    "oldest_upgradable_version": "19.0.1.0.0",
    "category": "Supply Chain/Inventory",
    "summary": "Read Tres Guerras shipment history and delivery evidence links",
    "description": "Adds Tres Guerras (Autotransportes de Carga Tresguerras) as a carrier tracking provider. Reads shipment status, service, origin, destination, weight, package count and movement history from the service the carrier's mobile app uses. Shows HTTPS links to available receipts and delivery evidence on known carrier hosts. Maps event codes to transfer status and distinguishes home delivery from pickup at the branch (Ocurre). Documents depend on what the carrier has published. Reads only: it books no shipment and touches no account. Set the provider on the carrier's form.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "delivery_tracking",
    ],
}
