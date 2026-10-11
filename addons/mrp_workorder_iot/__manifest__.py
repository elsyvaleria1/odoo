{
    "name": "Work Order IoT Camera and Trigger Integration",
    "version": "1.0",
    "category": "Supply Chain/Manufacturing",
    "sequence": 50,
    "summary": "Capture IoT camera images and expose device triggers in work order steps",
    "description": "Adds camera capture to picture checks, workcenter trigger information and IoT printer targeting for quality reports. The camera path requires a configured IoT box and device identifier; measurement handling may be supplied by additional quality extensions.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mrp_workorder",
        "quality_iot",
    ],
    "data": [
        "security/ir.access.csv",
        "views/mrp_workorder_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mrp_workorder_iot/static/src/**/*",
        ],
    },
    "auto_install": True,
}
