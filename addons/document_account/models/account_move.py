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
        # sudo() like every other document.document access in this model: the
        # flag answers "does this move have documents", not "may you read them",
        # and a restricted folder would otherwise hide the smart button from a
        # user who is entitled to the move.
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
            # The module's other two gates log their inputs; this one did not,
            # so "the main attachment was set and no document appeared" had no
            # entry anywhere and could only be answered by reading the branch.
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
                    # Search also in previous_attachment_ids to handle the case where
                    # the attachment is not the main one due to versioning
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
        """File the bill the alias just produced.

        `account` posts the alias message under `no_document=True` because one
        mail can become several moves and, until that is settled, no
        per-attachment decision can be right. Both of this module's gates read
        that flag and decline -- the attachment gate on mimetype
        (`message/rfc822` is neither a misc entry nor an e-invoice XML), the
        main-attachment gate on the flag itself -- so a vendor bill arriving on
        a journal alias got a move, got its attachment, and got no document at
        all. Measured with this module's own channels: one
        `move_document_gate by=create ... no_document=False` refusing on
        mimetype, then `move_main_attachment_gate ... no_document=True`.

        Here the regrouping is done, `self` is every move the mail produced and
        the flag is out of context, so the main attachment can be filed exactly
        as it is on every other path. `_update_or_create_document` finds an
        existing document for the attachment and updates it, so a move whose
        XML already produced one is not filed twice.
        """
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
        """When using the "Reconciliation Request" next activity on the statement line's chatter, the invoice is linked
        to this statement line through the 'suspense_statement_line_id' field.
        When checking this link on your invoice, you are able to click on a button triggering this method opening the
        bank reconciliation widget for this specific statement line to easily match it with the current invoice.

        :return: An action opening the bank reconciliation widget.
        """
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
        """``create_date`` is the transaction timestamp the record was created
        under, and ``cr.now()`` is the current one."""
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
                "active": True,  # if archived, unarchive it
                "folder_id": setting.folder_id.id,
                "partner_id": self.partner_id.id or doc_sudo.partner_id.id,
                "owner_id": self.create_uid.active and self.create_uid.id,
                "tag_ids": [Command.link(tag.id) for tag in setting.tag_ids],
            }
            if doc_sudo:
                _debug.lifecycle("move_document", by="updated", document=doc_sudo)
                # An existing document keeps its owner: the person who filed
                # it, not whoever created the move.
                del values["owner_id"]
                if (
                    doc_sudo.active
                    and not doc_sudo._is_in_journal_folder()
                    and not self._is_created_in_transaction()
                ):
                    # Somebody filed this document on purpose, outside any
                    # journal folder, onto a move that already existed.
                    # Becoming the main attachment must not pull it into the
                    # journal folder. A move created *from* the document, in
                    # this transaction, still takes the document with it.
                    del values["folder_id"]
                doc_sudo.write(values)
            else:
                _debug.lifecycle("move_document", by="created", move=self)
                # backward compatibility with documents that may be not
                # registered as attachments yet
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
        # One search for the whole batch: write() calls this for every move whose
        # partner changed, so searching per move is an N+1 on that path.
        docs_sudo = (
            self.env["document.document"]
            .sudo()
            .search([("attachment_id", "in", attachments.ids)])
        )
        doc_by_attachment = {}
        for doc in docs_sudo:
            # setdefault keeps the first row per attachment, which is the row the
            # previous per-move limit=1 search returned.
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
