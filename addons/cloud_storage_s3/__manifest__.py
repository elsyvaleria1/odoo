{
    "name": "S3 Attachment Storage",
    "version": "19.0.3.1.0",
    "oldest_upgradable_version": "19.0.3.1.0",
    "category": "Hidden/Tools",
    "summary": "Store attachments in S3 with optional local mirroring",
    "description": "Adds S3 configuration, attachment upload and access helpers, mirror queuing and bucket-import support over the cloud-storage dependency. Requires a configured bucket, region and credentials with suitable permissions. Storage and local-mirror behavior depend on the selected mode and successful background processing.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "cloud_storage",
        "credential",
    ],
    "external_dependencies": {
        "python": [
            "boto3",
        ],
    },
    "data": [
        "security/privileges.xml",
        "security/ir.access.csv",
        "data/credential_category_data.xml",
        "data/credential_category_field_data.xml",
        "data/ir_cron.xml",
        "views/settings.xml",
    ],
    "uninstall_hook": "uninstall_hook",
}
