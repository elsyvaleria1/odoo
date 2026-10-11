{
    "name": "IoT - Camera Capture",
    "category": "Supply Chain/IoT",
    "summary": "Capture images through the supplied IoT camera handler",
    "description": "Adds a Linux camera interface and capture driver for devices recognized by the IoT runtime. Requires a compatible camera and operating-system capture support. Business applications request captures through the IoT connection; the addon does not provide a standalone surveillance or video-recording application.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "iot",
    ],
    "iot_handlers_in_image": True,
}
