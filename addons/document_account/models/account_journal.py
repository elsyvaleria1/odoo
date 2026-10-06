from collections import defaultdict

from odoo import api, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    @api.model_create_multi
    def create(self, vals_list):
        journals = super().create(vals_list)
        journals.sudo()._documents_configure_sync()
        return journals

    def _documents_configure_sync(self) -> None:
        """Configure the synchronization of accounting with documents.

        * Create synchronization settings for the journals (skip if missing data).
        * Embed relevant server actions on the specific journal folder.
        * Embed relevant server actions on the company's parent 'Finance' folder.

        The setting carries a folder only. ``tag_ids`` stays available for
        whoever wants to tag a journal's documents by hand, but nothing here
        invents a tag: the journal of a document is already readable from the
        move it is linked to, so a tag repeating the journal name classifies
        nothing.
        """
        FolderSetting = self.env["document.account.folder.setting"]
        Journal = self.env["account.journal"]
        sync_journals = self.filtered(
            lambda j: j.type and j.name and j.company_id.account_folder_id
        )
        if not sync_journals:
            _debug.logic(
                "journal_sync_skipped", reason="no_eligible_journal", journals=self
            )
            return
        journal_type_labels = dict(
            Journal.fields_get(["type"], ["selection"])["type"]["selection"]
        )
        folders_by_journal_type = (
            sync_journals._documents_ensure_journal_folder_created(journal_type_labels)
        )
        actions_to_embed = self._documents_get_embed_on_sync_actions()

        settings_to_create = []
        folders_to_embed = defaultdict(lambda: self.env["document.document"])

        for journal in sync_journals:
            company = journal.company_id
            journal_type = journal.type
            target_folder = folders_by_journal_type[journal.company_id, journal.type]

            settings_to_create.append(
                {
                    "company_id": company.id,
                    "journal_id": journal.id,
                    "folder_id": target_folder.id,
                }
            )

            actions_xml_ids = actions_to_embed.get(journal_type, [])
            if not actions_xml_ids:
                continue

            for xml_id in actions_xml_ids:
                folders_to_embed[xml_id] |= target_folder | company.account_folder_id

        _debug.pipeline(
            "journal_sync",
            journals=sync_journals,
            settings=len(settings_to_create),
            action_ids=len(folders_to_embed),
        )
        if settings_to_create:
            FolderSetting.create(settings_to_create)

        for action_xml_id, folders in folders_to_embed.items():
            if action := self.env.ref(action_xml_id, raise_if_not_found=False):
                _debug.lifecycle(
                    "action_embedded", action=action_xml_id, folders=folders
                )
                folders._embed_action(action.id)

    @api.model
    def _documents_get_embed_on_sync_actions(self) -> dict:
        """Return a dictionary mapping journal types to action XML IDs to embed."""
        return {
            "purchase": [
                "document_account.ir_actions_server_create_vendor_bill",
                "document_account.ir_actions_server_create_vendor_refund",
            ],
            "sale": [
                "document_account.ir_actions_server_create_customer_invoice",
                "document_account.ir_actions_server_create_credit_note",
            ],
            "bank": [
                "document_account.ir_actions_server_bank_statement",
            ],
            "general": [
                "document_account.ir_actions_server_create_misc_entry",
            ],
        }

    def _documents_ensure_journal_folder_created(self, type_labels) -> dict:
        """Return the sync folder of every (company, journal type) of ``self``.

        A folder exists to be an access boundary or an entry point, never to
        classify, so a new journal reuses the folder the journals of its own
        type already use in its company instead of getting one of its own. Only
        when that company has no journal of the type configured yet does this
        fall back to adopting, and then to creating, the folder named after the
        journal type under the company's accounting folder.
        """
        FolderSetting = self.env["document.account.folder.setting"]
        Documents = self.env["document.document"]
        required_refs = set(self.mapped(lambda j: (j.company_id, j.type)))

        # The company that matters is the journal's own: a setting created by
        # hand defaults company_id to the active company, which may not be the
        # one of its journal, and such a setting must still be reused.
        existing_settings = FolderSetting.search(
            Domain.OR(
                [
                    [
                        ("journal_id.company_id", "=", c.id),
                        ("journal_id.type", "=", j_type),
                    ]
                    for c, j_type in required_refs
                ]
            ),
            order="create_date",
        )
        existing_settings = {
            (s.journal_id.company_id, s.journal_id.type): s.folder_id
            for s in existing_settings
        }

        existing_folders = Documents.search(
            Domain("id", "not in", FolderSetting._search([]).select("folder_id"))
            & Domain.OR(
                [
                    [
                        ("company_id", "=", company.id),
                        ("folder_id", "=", company.account_folder_id.id),
                        ("name", "=", type_labels[journal_type]),
                        ("type", "=", "folder"),
                    ]
                    for company, journal_type in required_refs
                ]
            ),
            order="create_date",
        )
        existing_folders = {(f.company_id, f.name): f for f in existing_folders}

        existing = {
            (company, journal_type): folder
            for company, journal_type in required_refs
            if (
                folder := existing_settings.get((company, journal_type))
                or existing_folders.get((company, type_labels[journal_type]))
            )
        }
        missing_refs = required_refs - existing.keys()
        _debug.pipeline(
            "journal_folders",
            required=len(required_refs),
            reused=len(existing),
            missing=len(missing_refs),
        )
        created = Documents.create(
            [
                {
                    "company_id": company.id,
                    "folder_id": company.account_folder_id.id,
                    "name": type_labels[journal_type],
                    "owner_id": False,
                    "type": "folder",
                }
                for company, journal_type in missing_refs
            ]
        )

        # Update translation of the created folders
        selection_options = (
            self.env["ir.model.fields.selection"]
            .sudo()
            .search(
                [
                    (
                        "field_id",
                        "=",
                        self.env.ref("account.field_account_journal__type").id,
                    )
                ]
            )
        )
        self._documents_sync_translations(selection_options, "name", created, "name")
        return {**existing, **dict(zip(missing_refs, created, strict=False))}

    def _documents_sync_translations(
        self, source_records, source_field, target_records, target_field
    ) -> None:
        """Copy the translation from source_records to target_records.

        Field values of the source_records must be aligned with those of the target_records for the main language.
        """
        sources = {
            r[source_field]: r for r in source_records.with_context(prefetch_langs=True)
        }
        for target_rec in target_records:
            value = target_rec[target_field]
            target_rec.update_field_translations(
                target_field,
                {
                    lang_code: sources[value].with_context(lang=lang_code)[source_field]
                    for lang_code, __ in self.env["res.lang"].get_installed()
                },
            )

    def create_document_from_attachment(self, attachment_ids=None):
        """When running an action on several documents, this method is called
        in a loop (because of the "multi" server action). When it is the
        case, we try to redirect to a list of all created records (journal
        entries or bank statements) instead of just the last one, using the
        context."""

        with _debug.perf("document_from_attachment", cr=self.env.cr, journals=self):
            action = super().create_document_from_attachment(attachment_ids)
        documents_active_ids = self.env.context.get("documents_active_ids", [])
        if (
            self.env.context.get("active_model") != "document.document"
            or len(documents_active_ids) <= 1
        ):
            return action

        account_move_ids = (
            self.env["document.document"].browse(documents_active_ids).mapped("res_id")
        )
        action.update(
            {
                "name": self.env._("Generated Bank Statements")
                if action.get("res_model", "") == "account.bank.statement"
                else action.get("name", ""),
                "domain": [("id", "in", account_move_ids)],
                "views": [[False, "list"], [False, "kanban"], [False, "form"]],
                "view_mode": "list,kanban,form",
            }
        )
        return action
