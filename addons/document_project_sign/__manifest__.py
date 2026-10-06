{
    "name": "Project Folder Signature Action",
    "version": "1.0",
    "category": "Productivity/Documents",
    "summary": "Expose the signature-template action on the project Documents folder",
    "description": "Embeds the Documents signature-template action on the project folder when the referenced records exist. The signing workflow and project document association are supplied by the dependencies.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "document_project",
        "document_sign",
    ],
    "data": [
        "data/ir_actions_server_data.xml",
    ],
    "auto_install": True,
}
