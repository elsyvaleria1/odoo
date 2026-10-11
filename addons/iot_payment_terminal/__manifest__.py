{
    "name": "IoT - Native Payment Terminal Base",
    "category": "Supply Chain/IoT",
    "summary": "Provide shared driver helpers for native-library payment terminals",
    "description": "Supplies a ctypes-based terminal driver base used by vendor-specific IoT addons. Handles common transaction and device behavior but does not identify or operate a terminal by itself. Requires a concrete terminal addon, its native library and a supported host platform.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "iot",
    ],
    "iot_handlers_in_image": True,
}
