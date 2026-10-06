{
    "name": "Azure Attachment Storage",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden/Tools",
    "summary": "Store eligible attachments in Azure Blob Storage",
    "description": "Implements signed upload and download URLs for an Azure storage account and container. Requires tenant and client credentials with access to that storage.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "credential",
        "cloud_storage",
    ],
    "data": [
        "views/settings.xml",
    ],
    "uninstall_hook": "uninstall_hook",
}
