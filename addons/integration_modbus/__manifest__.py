{
    "name": "Modbus Stream Protocol",
    "category": "Hidden/Tools",
    "summary": "Poll Modbus register blocks and send queued register or coil writes",
    "description": "Registers TCP and serial RTU adapters for integration streams using pymodbus. Configured subscriptions select holding registers, input registers, coils or discrete inputs; polling follows the stream heartbeat. Requires reachable compatible hardware, register addresses and an active integration stream worker.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "integration",
    ],
    "external_dependencies": {
        "python": [
            "pymodbus",
        ],
    },
    "auto_install": True,
}
