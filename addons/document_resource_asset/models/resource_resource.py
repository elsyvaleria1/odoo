from odoo import Command, api, fields, models


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = ["resource.resource", "mixin.documents"]

    document_ids = fields.One2many(
        comodel_name="document.document",
        inverse_name="res_id",
        string="Documents",
        domain=lambda self: [("res_model", "=", self._get_reference_model_name())],
    )
    count_document = fields.Count(
        count_of="document_ids",
        string="Document Count",
    )
    document_centralized = fields.Boolean(compute="_compute_document_centralized")

    @api.depends("kind_id", "company_id")
    def _compute_document_centralized(self) -> None:
        # one search for the page, not one per asset
        settings = self._document_settings_by_kind()
        for resource in self:
            resource.document_centralized = settings.get(
                (resource.kind_id.id, resource._documents_company().id),
                self.env["resource.kind.document"],
            ).centralize

    def _documents_company(self):
        return self.company_id or self.env.company

    def _get_document_setting(self):
        """The row naming where this kind of thing files its documents, in its
        company. Kinds with no row file nothing."""
        self.check_singleton()
        return self._document_settings_by_kind().get(
            (self.kind_id.id, self._documents_company().id),
            self.env["resource.kind.document"],
        )

    def _document_settings_by_kind(self) -> dict:
        """The settings rows of these things, by (kind id, company id)."""
        things = self.filtered("kind_id")
        if not things:
            return {}
        rows = (
            self.env["resource.kind.document"]
            .sudo()
            .search(
                [
                    ("kind_id", "in", things.kind_id.ids),
                    (
                        "company_id",
                        "in",
                        list({thing._documents_company().id for thing in things}),
                    ),
                ]
            )
        )
        return {(row.kind_id.id, row.company_id.id): row for row in rows}

    def _get_document_folder(self):
        if not self.kind_id:
            return super()._get_document_folder()
        return self._get_document_setting().folder_id

    def _get_document_tags(self):
        if not self.kind_id:
            return super()._get_document_tags()
        return self._get_document_setting().tag_ids

    def _get_document_owner(self):
        if not self.kind_id:
            return super()._get_document_owner()
        return self.env.user

    def _get_document_vals_access_rights(self):
        if not self.kind_id:
            return super()._get_document_vals_access_rights()
        return {
            "access_internal": "view",
            "access_via_link": "none",
        }

    def _prepare_asset_document_vals(self, name, **extra) -> dict:
        self.check_singleton()
        return {
            "name": name,
            "type": "binary",
            "res_model": self._get_reference_model_name(),
            "res_id": self.id,
            "folder_id": self._get_document_folder().id or False,
            "tag_ids": [Command.set(self._get_document_tags().ids)],
            "owner_id": self._get_document_owner().id,
            "company_id": self._documents_company().id,
            **self._get_document_vals_access_rights(),
            **extra,
        }

    def _file_document(self, name, **extra):
        return (
            self.env["document.document"]
            .sudo()
            .create(self._prepare_asset_document_vals(name, **extra))
            .with_env(self.env)
        )

    def _check_create_documents(self):
        return bool(
            self.kind_id
            and self._get_document_setting().centralize
            and super()._check_create_documents()
        )

    def action_view_documents(self):
        self.check_singleton()
        if not self.document_centralized:
            return True
        folder = self._get_document_folder()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "document.document_action"
        )
        action["domain"] = [
            "|",
            ("type", "=", "folder"),
            "&",
            ("res_model", "=", self._get_reference_model_name()),
            ("res_id", "=", self.id),
        ]
        action["context"] = {
            "default_res_id": self.id,
            "default_res_model": self._get_reference_model_name(),
            "searchpanel_default_user_folder_id": str(folder.id) if folder else False,
            "searchpanel_default_tag_ids": self._get_document_tags().ids,
        }
        return action
