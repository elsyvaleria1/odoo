{
    "name": "Devices - WebSocket",
    "version": "19.0.2.0.0",
    "oldest_upgradable_version": "19.0.2.0.0",
    "category": "Supply Chain/IoT",
    "summary": "Connect device records to WebSocket streams and queue outgoing frames",
    "description": "Builds a ws:// endpoint from the device host, port and path, with configured heartbeat and optional basic or bearer authentication. Connect and disconnect actions change stream activation; reads expose stream status and sends enqueue frames. Requires the integration stream worker and a compatible reachable endpoint.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "integration_websocket",
        "device",
    ],
    "data": [
        "views/device_device_views.xml",
    ],
}
