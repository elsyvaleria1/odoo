{
    "name": "Asset GPS Tracking",
    "version": "19.0.1.16.0",
    "oldest_upgradable_version": "19.0.1.12.0",
    "category": "Supply Chain/IoT",
    "summary": "Link assets to GPS devices and expose tracking readings and history",
    "description": "Adds a GPS-device link and related telemetry to resource assets and their stock-lot interfaces. Extends GPS reports with asset identity and provides a scheduled odometer-recording action. Requires a configured GPS device and incoming telemetry; this bridge does not itself obtain positions from tracker hardware.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "OPL-1",
    "depends": [
        "asset_ledger",
        "device_gps",
    ],
    "data": [
        "security/legacy_privilege_aliases.xml",
        "data/product_asset_gps_cron.xml",
        "views/resource_asset_views.xml",
        "views/device_device_views.xml",
        "reports/device_data_log_gps_report_views.xml",
    ],
}
