{
    "name": "POS Event Badge IoT Printing",
    "version": "1.0",
    "category": "Marketing/Events",
    "summary": "Print event badges from POS receipts through IoT",
    "description": "Extends the POS receipt screen with event badge printing and loads the event badge format into POS data. Printing attendee badges updates attendance; a configured report and compatible IoT printer are required for device output.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "iot",
        "pos_event",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_event_iot/static/src/**/*",
        ],
    },
    "auto_install": True,
}
