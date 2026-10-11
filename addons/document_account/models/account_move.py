from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "mixin.documents.unlink"]

    suspense_statement_line_id = fields.Many2one(
        comodel_name="account.bank.statement.line",
        string="Request document from a bank statement line",
        index="btree_not_null",
    )

    has_documents = fields.Boolean(compute="_compute_has_documents")

    @api.depends("attachment_ids")
    def _compute_has_documents(self) -> None:
        result = (
            self.env["document.document"]
            .sudo()
            ._read_group(
                domain=[("res_model", "=", self._name), ("res_id", "in", self.ids)],
                groupby=["res_id"],
            )
        )
        has_documents_ids = {r[0] for r in result}
        for move in self:
            move.has_documents = move.id in has_documents_ids

    def write(self, vals):
        main_attachment_id = vals.get("message_main_attachment_id")
        new_documents = [False] * len(self)
        journals_changed = [
            ("journal_id" in vals and move.journal_id.id != vals["journal_id"])
            for move in self
        ]
        moves_with_updated_partner = self.filtered(
            lambda move: (
                vals.get("partner_id", move.partner_id.id) != move.partner_id.id
            )
        )
        for i, move in enumerate(self):
            if _debug.logic.enabled and "message_main_attachment_id" in vals:
                _debug.logic(
                    "move_main_attachment_gate",
                    move=move,
                    move_type=move.move_type,
                    requested=main_attachment_id,
                    previous=move.message_main_attachment_id.id,
                    no_document=bool(move.env.context.get("no_document")),
                )
            if (
                main_attachment_id
                and not move.env.context.get("no_document")
                and move.move_type != "entry"
            ):
                previous_attachment_id = move.message_main_attachment_id.id
                if previous_attachment_id == main_attachment_id:
                    continue
                document = False
                if previous_attachment_id:
                    document = (
                        move.env["document.document"]
                        .sudo()
                        .search(
                            [
                                "|",
                                ("attachment_id", "=", previous_attachment_id),
                                (
                                    "previous_attachment_ids",
                                    "in",
                                    previous_attachment_id,
                                ),
                            ],
                            limit=1,
                        )
                    )
                if document:
                    document.attachment_id = main_attachment_id
                else:
                    new_documents[i] = True
        res = super().write(vals)
        for new_document, journal_changed, move in zip(
            new_documents, journals_changed, self, strict=False
        ):
            if (new_document or journal_changed) and move.message_main_attachment_id:
                move._update_or_create_document(move.message_main_attachment_id.id)
        for move in moves_with_updated_partner:
            move._sync_partner_on_document()
        return res

    def _message_post_from_alias_done(self) -> None:
        super()._message_post_from_alias_done()
        for move in self:
            if move.move_type == "entry" or not move.message_main_attachment_id:
                continue
            _debug.pipeline(
                "move_document_from_alias",
                move=move,
                move_type=move.move_type,
                attachment=move.message_main_attachment_id.id,
            )
            move._update_or_create_document(move.message_main_attachment_id.id)

    def button_reconcile_with_st_line(self):
        self.check_singleton()
        st_line = self.suspense_statement_line_id
        rec_pay_lines = self.line_ids.filtered(
            lambda x: (
                x.account_id.account_type in ("asset_receivable", "liability_payable")
            )
        )
        default_todo_command = ",".join(
            ["add_new_amls"] + [str(x) for x in rec_pay_lines.ids]
        )
        return self.env[
            "account.bank.statement.line"
        ]._action_view_bank_reconciliation_widget(
            default_context={
                "search_default_journal_id": st_line.journal_id.id,
                "search_default_statement_id": st_line.statement_id.id,
                "default_journal_id": st_line.journal_id.id,
                "default_st_line_id": st_line.id,
                "default_todo_command": default_todo_command,
            },
        )

    def _is_created_in_transaction(self) -> bool:
        self.check_singleton()
        return self.create_date == self.env.cr.now()

    def _update_or_create_document(self, attachment_id) -> None:
        setting = (
            self.env["document.account.folder.setting"]
            .sudo()
            .search(
                [
                    ("journal_id", "=", self.journal_id.id),
                    ("company_id", "=", self.company_id.id),
                ],
                limit=1,
            )
        )
        if _debug.logic.enabled and not setting:
            _debug.logic("move_document_skipped", reason="no_folder_setting", move=self)
        if setting:
            Documents_sudo = self.env["document.document"].sudo()
            doc_sudo = Documents_sudo.with_context(active_test=False).search(
                [("attachment_id", "=", attachment_id)], limit=1
            )
            values = {
                "active": True,
                "folder_id": setting.folder_id.id,
                "partner_id": self.partner_id.id or doc_sudo.partner_id.id,
                "owner_id": self.create_uid.active and self.create_uid.id,
                "tag_ids": [Command.link(tag.id) for tag in setting.tag_ids],
            }
            if doc_sudo:
                _debug.lifecycle("move_document", by="updated", document=doc_sudo)
                del values["owner_id"]
                if (
                    doc_sudo.active
                    and not doc_sudo._is_in_journal_folder()
                    and not self._is_created_in_transaction()
                ):
                    del values["folder_id"]
                doc_sudo.write(values)
            else:
                _debug.lifecycle("move_document", by="created", move=self)
                values.update(
                    {
                        "attachment_id": attachment_id,
                        "company_id": self.company_id.id,
                    }
                )
                doc_sudo.create(values)

    def _sync_partner_on_document(self) -> None:
        attachments = self.message_main_attachment_id
        if not attachments:
            _debug.logic("partner_sync_skipped", reason="no_attachment", moves=self)
            return
        docs_sudo = (
            self.env["document.document"]
            .sudo()
            .search([("attachment_id", "in", attachments.ids)])
        )
        doc_by_attachment = {}
        for doc in docs_sudo:
            doc_by_attachment.setdefault(doc.attachment_id.id, doc)
        for move in self:
            doc = doc_by_attachment.get(move.message_main_attachment_id.id)
            if not doc or doc.partner_id == move.partner_id:
                continue
            _debug.lifecycle(
                "document_partner_synced", document=doc, partner=move.partner_id
            )
            doc.partner_id = move.partner_id

    def action_view_documents_account_move(self) -> dict:
        self.check_singleton()
        domain = [("res_model", "=", self._name), ("res_id", "=", self.id)]
        documents = self.env["document.document"].search(domain)
        default_user_folder_id = (
            documents[0].user_folder_id
            if len(set(documents.mapped("user_folder_id"))) == 1
            else False
        )

        return {
            **self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "document.document_action_preference"
            ),
            "domain": domain,
            "context": {"searchpanel_default_user_folder_id": default_user_folder_id},
        }
