{
    "name": "WebSocket Stream Protocol",
    "category": "Hidden/Tools",
    "summary": "Exchange text and binary frames through configured WebSocket streams",
    "description": "Registers ws and wss connections using websocket-client, with optional Basic or Bearer credentials, custom headers and heartbeat pings. Incoming messages become stream frames and queued frames select text or binary output; requires a compatible endpoint and an active integration stream worker.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "integration",
    ],
    "external_dependencies": {
        "python": [
            "websocket",
        ],
    },
    "auto_install": True,
}
