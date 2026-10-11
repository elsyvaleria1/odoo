{
    "name": "Work Order Quality IoT Measurements",
    "category": "Supply Chain/Quality",
    "summary": "Read IoT measurements from work order quality checks",
    "description": "Extends the manufacturing quality-check interface to request a device measurement and write its returned value to the check. Also adds pass, fail and take-measure action choices to IoT triggers. Measurement capture requires a configured IoT box and device identifier.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "quality_mrp_workorder",
        "quality_control_iot",
        "mrp_workorder_iot",
    ],
    "assets": {
        "web.assets_backend": [
            "quality_mrp_workorder_iot/static/src/**/*",
        ],
    },
    "auto_install": True,
}
