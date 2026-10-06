{
    "name": "MQTT Stream Protocol",
    "category": "Hidden/Tools",
    "summary": "Subscribe to MQTT topics and publish queued stream messages",
    "description": "Registers MQTT 5 connections through paho for mqtt and mqtts URLs, with configured topic subscriptions, credentials and TLS settings. Outgoing messages require a topic in frame metadata or stream configuration; a reachable broker and active integration stream worker are required.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "integration",
    ],
    "external_dependencies": {
        "python": [
            "paho-mqtt",
        ],
    },
    "auto_install": True,
}
