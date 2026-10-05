from odoo import Command

from . import models


KIND_BY_FOLDER_XMLID = {
    "asset_ledger_document.document_folder_equipment": (
        "resource_asset.kind_equipment",
        "resource_asset.kind_tool",
        "resource_asset.kind_it",
    ),
    "asset_ledger_document.document_folder_fleet": ("resource_asset.kind_vehicle",),
    "asset_ledger_document.document_folder_machinery": (
        "resource_asset.kind_machinery",
    ),
    "asset_ledger_document.document_folder_property": ("resource_asset.kind_property",),
}
TAG_XMLID_BY_FOLDER_XMLID = {
    "asset_ledger_document.document_folder_equipment": "asset_ledger_document.documents_tag_equipment_doc",
    "asset_ledger_document.document_folder_fleet": "asset_ledger_document.documents_tag_fleet_doc",
    "asset_ledger_document.document_folder_machinery": "asset_ledger_document.documents_tag_machinery_doc",
    "asset_ledger_document.document_folder_property": "asset_ledger_document.documents_tag_property_doc",
}


def _documents_product_asset_post_init(env) -> None:
    """Give each kind of asset the folder this module used to keep per bucket."""
    settings = env["resource.kind.document"]
    existing = {(row.kind_id.id, row.company_id.id) for row in settings.search([])}
    vals_list = []
    for company in env["res.company"].search([]):
        for folder_xmlid, kind_xmlids in KIND_BY_FOLDER_XMLID.items():
            folder = env.ref(folder_xmlid, raise_if_not_found=False)
            tag = env.ref(
                TAG_XMLID_BY_FOLDER_XMLID[folder_xmlid], raise_if_not_found=False
            )
            if not folder:
                continue
            for kind_xmlid in kind_xmlids:
                kind = env.ref(kind_xmlid, raise_if_not_found=False)
                if not kind or (kind.id, company.id) in existing:
                    continue
                existing.add((kind.id, company.id))
                vals_list.append(
                    {
                        "kind_id": kind.id,
                        "company_id": company.id,
                        "folder_id": folder.id,
                        "tag_ids": [Command.set(tag.ids if tag else [])],
                    }
                )
    settings.create(vals_list)
