from dataclasses import dataclass

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


@dataclass(frozen=True)
class DocumentLink:
    tag_xmlid: str
    name_field: str
    strip_prefix: str = ""


DOCUMENT_LINKS: dict[str, DocumentLink] = {
    "fuel_card_id": DocumentLink(
        tag_xmlid="asset_ledger_document.documents_tag_fuel_card",
        name_field="fuel_card_name",
        strip_prefix="Efecticard ",
    ),
    "highway_pass_id": DocumentLink(
        tag_xmlid="asset_ledger_document.documents_tag_highway_pass",
        name_field="highway_pass_name",
        strip_prefix="IMDM ",
    ),
    "property_deed_id": DocumentLink(
        tag_xmlid="asset_ledger_document.documents_tag_property_deed",
        name_field="property_deed_name",
    ),
    "lease_agreement_id": DocumentLink(
        tag_xmlid="asset_ledger_document.documents_tag_lease_agreement",
        name_field="lease_agreement_name",
    ),
    "building_permit_id": DocumentLink(
        tag_xmlid="asset_ledger_document.documents_tag_building_permit",
        name_field="building_permit_name",
    ),
}


def _document_link(field_name: str, **kwargs) -> fields.Many2one:
    return fields.Many2one(
        comodel_name="document.document",
        inverse="_inverse_document_links",
        domain=lambda self: self._document_tag_domain(
            DOCUMENT_LINKS[field_name].tag_xmlid
        ),
        **kwargs,
    )


class ResourceAsset(models.Model):
    _name = "resource.asset"
    _inherit = ["resource.asset", "mixin.documents"]

    fuel_card_id = _document_link(
        "fuel_card_id",
    )
    fuel_card_name = fields.Char(
        compute="_compute_document_link_names",
        store=True,
    )
    highway_pass_id = _document_link(
        "highway_pass_id",
    )
    highway_pass_name = fields.Char(
        compute="_compute_document_link_names",
        store=True,
    )
    property_deed_id = _document_link(
        "property_deed_id",
        help="Property deed or title document",
    )
    property_deed_name = fields.Char(
        compute="_compute_document_link_names",
        store=True,
    )
    lease_agreement_id = _document_link(
        "lease_agreement_id",
        help="Current lease or rental agreement",
    )
    lease_agreement_name = fields.Char(
        compute="_compute_document_link_names",
        store=True,
    )
    building_permit_id = _document_link(
        "building_permit_id",
        help="Building or construction permit",
    )
    building_permit_name = fields.Char(
        compute="_compute_document_link_names",
        store=True,
    )

    def _document_tag_domain(self, tag_xmlid: str) -> list:
        tag = self.env.ref(tag_xmlid, raise_if_not_found=False)
        return [("tag_ids", "in", tag.ids)] if tag else [(1, "=", 0)]

    def _compute_document_link_name(self, field_name: str) -> None:
        link = DOCUMENT_LINKS[field_name]
        for asset in self:
            name = ""
            if asset[field_name]:
                name = asset[field_name].name.split(".", 1)[0]
                if link.strip_prefix:
                    name = name.replace(link.strip_prefix, "")
            asset[link.name_field] = name

    def _link_document(self, field_name: str) -> None:
        for asset in self:
            document = asset[field_name]
            if document:
                _debug.lifecycle(
                    "asset_document_linked",
                    asset=asset,
                    document=document,
                    slot=field_name,
                )
                document.sudo().write(
                    {
                        "res_model": asset._get_reference_model_name(),
                        "res_id": asset.id,
                        "is_editable_attachment": True,
                    },
                )

    @api.depends(*DOCUMENT_LINKS)
    def _compute_document_link_names(self) -> None:
        for field_name in DOCUMENT_LINKS:
            self._compute_document_link_name(field_name)

    def _inverse_document_links(self) -> None:
        # One inverse for every slot: linking is idempotent, and Odoo gives the
        # inverse no way to know which of the five was written.
        for field_name in DOCUMENT_LINKS:
            self._link_document(field_name)

    def _get_document_vals_access_rights(self) -> dict:
        return {
            "access_internal": "view",
            "access_via_link": "none",
        }
