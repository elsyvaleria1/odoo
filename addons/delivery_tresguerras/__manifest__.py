{
    "name": "Tres Guerras Tracking",
    "version": "19.0.1.0.0",
    "oldest_upgradable_version": "19.0.1.0.0",
    "category": "Supply Chain/Inventory",
    "summary": "Read Tres Guerras shipment status into transfers",
    "description": "Adds Tres Guerras (Autotransportes de Carga Tresguerras) as a carrier tracking provider. Reads the last event of a tracking number from the public tracking service the carrier's mobile app uses, maps its event codes to the transfer's carrier status and tells home delivery from pickup at the branch (Ocurre). Reads only: it books no shipment and touches no account. Set the provider on the carrier's form.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "delivery_tracking",
    ],
}
