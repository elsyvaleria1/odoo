from odoo import models


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = ["resource.resource", "mixin.documents"]

    # An asset shares its resource's id, so its documents and attachments are
    # filed under the resource; the asset still says where they go, until the
    # kind is the resource's.
    def _get_document_asset(self):
        self.check_singleton()
        return self.asset_id._get_concrete() if self.asset_id else self.asset_id

    def _check_create_documents(self):
        asset = self._get_document_asset()
        return bool(asset) and asset._check_create_documents()

    def _get_document_folder(self):
        if asset := self._get_document_asset():
            return asset._get_document_folder()
        return super()._get_document_folder()

    def _get_document_tags(self):
        if asset := self._get_document_asset():
            return asset._get_document_tags()
        return super()._get_document_tags()

    def _get_document_owner(self):
        if asset := self._get_document_asset():
            return asset._get_document_owner()
        return super()._get_document_owner()

    def _get_document_partner(self):
        if asset := self._get_document_asset():
            return asset._get_document_partner()
        return super()._get_document_partner()

    def _get_document_vals_access_rights(self):
        if asset := self._get_document_asset():
            return asset._get_document_vals_access_rights()
        return super()._get_document_vals_access_rights()
