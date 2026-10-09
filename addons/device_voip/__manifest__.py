{
    "name": "Phone System Calls in the Softphone",
    "version": "19.0.1.2.0",
    "category": "Productivity/Phone",
    "summary": "Join what a phone system reports to the softphone's own calls, and provision a handset's softphone",
    "description": "A call the phone system reports names the extension that answered it: the extension's user answers for it, and a call the softphone already filed is completed instead of duplicated, so its recording lands on it. A company handset fetches its softphone settings, the extension and secret of its user, from the device configuration route.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "device_phone_call",
        "voip",
    ],
    "data": [
        "security/security.xml",
        "security/ir.access.csv",
    ],
    "auto_install": True,
}
