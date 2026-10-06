{
    "name": "IoT - Ingenico Payment Terminal",
    "category": "Supply Chain/IoT",
    "summary": "Handle supported Ingenico terminal actions over a socket connection",
    "description": "Supplies an IoT payment-terminal driver and transaction message handling for the implemented Ingenico protocol. Requires a compatible configured terminal and working IoT connection. Point-of-sale usage also requires the corresponding Ingenico POS integration and provider setup.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "iot",
    ],
    "iot_handlers_in_image": True,
}
