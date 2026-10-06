{
    "name": "POS Adam Scale Dependencies",
    "category": "Sales/Point of Sale",
    "summary": "Install Adam scale driver support alongside POS IoT integration",
    "description": "Combines the IoT Adam scale driver and POS IoT dependencies. It defines no additional driver or POS implementation. Using an Adam serial scale requires compatible connected hardware and configuration in the dependency modules.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "iot_adam_scale",
        "pos_iot",
    ],
}
