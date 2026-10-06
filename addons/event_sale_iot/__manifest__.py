{
    "name": "Event Sales Badge Print Guard",
    "version": "1.0",
    "category": "Marketing/Events",
    "summary": "Prevent automatic badge printing while an event registration requires payment",
    "description": "Patches the event registration summary dialog to disable automatic printing when its has_to_pay flag is set. Event sales supplies this flag for registrations with sale status to_pay; badge design and printer support come from other addons.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "iot",
        "event_sale",
    ],
    "assets": {
        "web.assets_backend": [
            "event_sale_iot/static/src/**/*",
        ],
    },
    "auto_install": True,
}
