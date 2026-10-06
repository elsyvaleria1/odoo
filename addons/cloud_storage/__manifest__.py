{
    "name": "Cloud Attachment Storage",
    "version": "1.0",
    "category": "Hidden/Tools",
    "summary": "Route eligible attachment uploads to a configured cloud provider",
    "description": "Adds cloud attachment types, upload and download hooks and a minimum-file-size setting. A provider addon and storage configuration are required.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mail",
    ],
    "data": [
        "views/settings.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "cloud_storage/static/src/core/common/**/*",
            "cloud_storage/static/src/**/web_portal/**/*",
        ],
        "mail.assets_public": [
            "cloud_storage/static/src/core/common/**/*",
        ],
    },
}
