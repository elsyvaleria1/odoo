{
    "name": "IoT - Six Payment Terminals",
    "category": "Supply Chain/IoT",
    "summary": "Handle Six terminal transactions through the TIM library",
    "description": "Adds TIM interface discovery and terminal transaction, cancellation and balance actions using the native library loader. Requires a compatible terminal, the TIM library and the IoT runtime. The corresponding POS addon connects these device actions to point-of-sale payments.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "iot_payment_terminal",
    ],
    "iot_handlers_in_image": True,
}
