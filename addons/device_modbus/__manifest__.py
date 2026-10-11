{
    "name": "Devices - Modbus",
    "version": "19.0.2.0.0",
    "oldest_upgradable_version": "19.0.2.0.0",
    "category": "Supply Chain/IoT",
    "summary": "Configure Modbus TCP and RTU device streams and queue register writes",
    "description": "Maps device endpoints, unit IDs, register types and polling intervals to integration streams. Incoming register values are stored as device data points; read actions activate the stream and return the last stored reading. Requires a reachable Modbus device or serial port and the integration stream worker; writes are queued for that worker.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "integration_modbus",
        "device",
    ],
    "data": [
        "data/device_kind_data.xml",
        "views/device_device_views.xml",
    ],
    "demo": [
        "demo/device_demo.xml",
    ],
}
