{
    "name": "Machine Counter Telemetry",
    "version": "19.0.1.7.2",
    "oldest_upgradable_version": "19.0.1.7.1",
    "category": "Supply Chain/IoT",
    "sequence": 11,
    "summary": "Aggregate MQTT machine counters and attribute readings to manufacturing work orders",
    "description": "Consumes the supported PLC counter payload through device MQTT streams, storing timestamped readings and hourly counter buckets with reset handling. Links configured devices to work centers and records counters against active work orders for quantity and rate reporting. Requires matching payload identifiers, MQTT credentials, certificates where configured and a running stream worker.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "device",
        "device_mqtt",
        "credential",
        "certificate",
        "mrp",
    ],
    "data": [
        "security/ir.access.csv",
        "data/device_kind_data.xml",
        "data/device_profile_data.xml",
        "views/device_machine_bucket_views.xml",
        "views/device_device_views.xml",
        "views/mrp_workorder_views.xml",
        "views/device_machine_workorder_views.xml",
        "views/device_machines_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "device_machines/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "device_machines/static/tests/**/*",
        ],
    },
}
