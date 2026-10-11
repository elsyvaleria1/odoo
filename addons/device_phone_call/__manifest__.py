{
    "name": "Device Phone Calls",
    "version": "19.0.1.2.0",
    "category": "Supply Chain/IoT",
    "summary": "File the calls and recordings a company handset or a phone system reports",
    "description": "Adds authenticated device routes for call-log batches and call recordings, on the companion app's wire contract, and the phone-system device category. Each reported call becomes a phone call of the device's company, matched to a contact and to the device's user; a recording is filed on the call it belongs to, and one that arrives ahead of its call-log entry makes a call that the entry completes on arrival.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "integration",
        "device",
        "phone_call",
    ],
    "data": [
        "security/security.xml",
        "security/ir.access.csv",
        "data/device_kind_data.xml",
        "data/ir_cron_data.xml",
        "views/phone_call_views.xml",
        "views/device_device_views.xml",
        "views/device_phone_call_menus.xml",
    ],
}
