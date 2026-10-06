{
    "name": "Asset Device Identity",
    "version": "19.0.1.4.1",
    "oldest_upgradable_version": "19.0.1.4.0",
    "category": "Supply Chain/IoT",
    "summary": "Link registered devices to their physical assets",
    "description": "Links a device to its own asset and reads serial number, IMEI and plate from that asset. Validates identity consistency and adds navigation between devices and assets.",
    "author": "AgroMarin",
    "website": "https://agromarin.mx",
    "license": "OPL-1",
    "depends": [
        "device_resource",
        "asset_ledger",
    ],
    "data": [
        "views/device_device_views.xml",
        "views/resource_asset_views.xml",
    ],
    "auto_install": True,
}
