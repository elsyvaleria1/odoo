{
    "name": "Devices - MQTT",
    "version": "19.0.2.1.0",
    "oldest_upgradable_version": "19.0.2.0.0",
    "category": "Supply Chain/IoT",
    "summary": "Configure device MQTT subscriptions and queue outgoing messages",
    "description": "Maps device and profile settings to MQTT streams, including broker URL, TLS selection, topics, client ID, QoS and optional credentials. Connect actions activate streams and send actions enqueue frames; read actions return stream status. Requires a reachable broker, appropriate topics and a running integration stream worker.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "integration_mqtt",
        "device",
    ],
    "data": [
        "data/device_kind_data.xml",
        "views/device_views.xml",
    ],
    "demo": [
        "demo/device_profile_demo.xml",
        "demo/device_device_demo.xml",
        "demo/device_data_log_demo.xml",
    ],
}
