{
    "name": "Asset Document Filing",
    "version": "1.0",
    "category": "Productivity/Documents",
    "summary": "File asset documents by asset kind and company settings",
    "description": "Adds per-kind, per-company centralization settings, folders and tags, plus asset document links and navigation. Automatic document creation requires centralization to be enabled for the asset kind in its company; kinds without a settings row do not enable it.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "document",
        "resource_mail",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_actions_server_data.xml",
        "views/resource_asset_kind_views.xml",
        "views/resource_asset_views.xml",
    ],
    "auto_install": True,
    "post_init_hook": "_document_resource_asset_post_init",
}
