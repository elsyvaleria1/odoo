{
    "name": "IoT - Worldline Payment Terminals",
    "category": "Supply Chain/IoT",
    "summary": "Handle Worldline terminal transactions through the CTEP library",
    "description": "Adds platform-specific CTEP interfaces and terminal drivers for Linux and Windows, including transaction and cancellation calls. Requires the matching native vendor library, compatible hardware and IoT runtime. The corresponding POS integration supplies the payment-screen workflow.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "iot_payment_terminal",
    ],
    "iot_handlers_in_image": True,
}
