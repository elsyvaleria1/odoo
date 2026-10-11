{
    "name": "Company Phone Telemetry",
    "version": "19.0.2.1.0",
    "category": "Supply Chain/IoT",
    "summary": "Receive phone locations from a companion client, and file its calls and recordings",
    "description": "Adds the company-phone device category, the number of its SIM, and its authenticated location upload, storing GPS points. The handset's call log and recordings arrive on the device call routes and become phone calls. Requires a provisioned device and compatible companion client; recording capture and handset permissions belong to that client and its device environment.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "integration",
        "device",
        "device_gps",
        "device_phone_call",
    ],
    "data": [
        "data/device_kind_data.xml",
        "views/device_device_views.xml",
    ],
}
