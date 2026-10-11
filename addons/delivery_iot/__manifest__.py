{
    "name": "Delivery IoT Weighing and Printing",
    "version": "1.0",
    "category": "Supply Chain/IoT",
    "summary": "Read package weights and print available shipping documents through configured IoT devices",
    "description": "Adds scale selection to package preparation and optional automatic printing of carrier labels and export documents. Requires compatible configured scales or printers, printer assignments and operation-type settings; shipping document availability depends on the carrier and destination.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "iot",
        "stock_delivery",
    ],
    "data": [
        "reports/delivery_carrier_reports.xml",
        "wizards/wizard_stock_move_line_put_in_pack_views.xml",
        "views/iot_views.xml",
        "views/stock_menu_views.xml",
        "views/stock_picking_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "delivery_iot/static/src/**/*",
        ],
    },
    "auto_install": True,
}
