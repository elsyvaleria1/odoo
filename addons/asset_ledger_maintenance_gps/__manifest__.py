{
    "name": "Maintenance GPS Odometer Fallback",
    "version": "19.0.1.4.0",
    "category": "Supply Chain/Maintenance",
    "summary": "Read GPS odometers when an asset maintenance plan has no meter value",
    "description": "Extends maintenance-plan odometer calculation with the GPS reading from the asset stock lot. The fallback applies only when the normal calculation yields no current odometer.",
    "author": "AgroMarin",
    "license": "OPL-1",
    "depends": [
        "asset_ledger_maintenance",
        "asset_gps",
    ],
    "auto_install": True,
}
