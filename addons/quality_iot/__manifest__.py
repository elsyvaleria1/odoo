{
    "name": "Quality Check IoT Device Links",
    "category": "Supply Chain/IoT",
    "summary": "Associate quality control points and checks with IoT devices",
    "description": "Adds device selection on quality control points and device connection information on checks. Device forms expose linked control points; using measurements or camera input requires compatible configured IoT hardware and the relevant check interface.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "iot_sylvac",
        "iot_camera",
        "iot",
        "quality",
    ],
    "data": [
        "views/iot_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "quality_iot/static/src/**/*",
        ],
    },
    "auto_install": [
        "iot",
        "quality",
    ],
}
