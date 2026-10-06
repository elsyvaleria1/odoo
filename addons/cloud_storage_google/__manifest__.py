{
    "name": "Google Cloud Attachment Storage",
    "version": "1.0",
    "category": "Hidden/Tools",
    "summary": "Store eligible attachments in Google Cloud Storage",
    "description": "Implements signed upload and download URLs for a configured bucket. Requires a service-account key with the necessary bucket access.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "cloud_storage",
    ],
    "external_dependencies": {
        "python": [
            "google-auth",
        ],
        "apt": {
            "google-auth": "python3-google-auth",
        },
    },
    "data": [
        "views/settings.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "cloud_storage_google/static/src/**/*",
        ],
    },
    "uninstall_hook": "uninstall_hook",
}
